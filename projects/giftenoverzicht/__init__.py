#!/usr/local/bin/python3.6
import smtplib
import markdown
import shutil
import logging
import json
import threading
import os.path
import os
import urllib
from decimal import Decimal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate

from pony import orm
import cherrypy
from cherrypy.lib.static import serve_file
import calendar

from admingen.clients.exact_rest import (authenticateExact, getUsers, getTransactions,
                                         checkAuthorization, getAccounts)
from admingen.htmltools import *
from admingen import config
from admingen.clients import smtp
from admingen.keyring import KeyRing
from .giften import (generate_overviews, generate_overview, amount2Str, pdfUrl,
                    odataDate2Datetime, generate_pdfs, pdfName, PDF_DIR)
from . import model
from .model import SystemStates

from dataclasses import dataclass, asdict, fields

# FIXME: make the download files un-guessable (use crypto hash with salt as file name)
# FIXME: cherrypy toont nog veel debug informatie.

# TODO: store financial details in encrypted files.
# TODO: unlock keychain with in-process password (?)
# TODO: allow the year to be entered as $jaar oid.
# TODO: Selections alleen de waarde laten zien wanneer readonly
# TODO: Maak loggen configureerbaar via de settings.json
# TODO: selecteren / deselecteren van mensen om te mailen

# DONE: exact en SMTP secrets worden opgeslagen in een versleuteld file.
# DONE: Either allow an Exact or Local login for administration.
# DONE: check exact user has rights to the current administration
# DONE: Uploaden van logo's
# DONE: add a delay to downloading an overview to defeat brute-force attacks
# DONE: require a login to download overzichten


logging.getLogger().setLevel(logging.DEBUG)

USERS_FILE = '{}/{}.users.json'
TRANSACTIONS_FILE = '{}/{}.transactions.json'
ACCOUNTS_FILE = '{}/{}.accounts.json'


@dataclass
class SmtpDetails:
    id       : str
    name     : str
    smtphost : str
    user     : str
    password : str



def constructMail(md_msg, fname, **headers):
    # TODO: Add support for multiple recipients
    # We are using the old API for constructing emails:
    # the new one does not encode PDF attachments correctly.

    outer = MIMEMultipart()
    for key, value in headers.items():
        outer[key] = value

    outer['Date'] = formatdate(localtime=True)
    html_msg = markdown.markdown(md_msg)
    overzicht = open(fname, 'rb').read()

    # parts = [': '.join(h) for h in zip(headers, details)]
    text_parts = MIMEMultipart('alternative')
    msg_plain = MIMEText(md_msg)
    msg_html = MIMEText(html_msg, 'html')
    text_parts.attach(msg_plain)
    text_parts.attach(msg_html)
    outer.attach(text_parts)

    # Attach the actual overview file.
    overzicht_part = MIMEApplication(overzicht, 'pdf', name=fname)
    outer.attach(overzicht_part)

    return outer


def periode_validator():
    return Verify(GreaterEqual('until', 'from'),
                  IsInteger('from', 1, 12),
                  IsInteger('until', 1, 12),
                  IsInteger('year', 2000, 2100),
                  )


def verstuur_validator():
    return Verify(IsEmailaddress('mailfrom'),
                  IsUrl('smtphost'),
                  IsSingleWord('user')
                  )


def overzicht(data):
    def overzichtregel(data):
        user_id = data[0]
        if data[2] and '@' in data[2]:
            query = urllib.parse.urlencode({'file': data[-1],
                                            'name': data[1],
                                            'mailto': data[2]})
            button = Button('<i class="fa fa-paper-plane"></i>', btn_type=['success', 'xs'],
                            target='/versturen?%s' % query)()
        else:
            button = ''
        return [*data[:-2], DownloadLink('pdf', data[-2]), button]

    return Title('Giften Overzicht'), \
           Button('Nieuw Overzicht', '/restart'), \
           Button('<i class="fa fa-paper-plane"> Alles Versturen</i>', btn_type='success',
                  target='/versturen'), \
           PaginatedTable(overzichtregel, data,
                          ['Relatie', 'Naam', 'email', 'Giften', 'overzicht', 'versturen'])


def load_mock(org_id, *args, **kwargs):
    time.sleep(4)
    Worker.setState(org_id, SystemStates.GeneratingPDF)
    time.sleep(4)
    Worker.setState(org_id, SystemStates.PDFCreated)


def verstuur_overzicht(**extra):
    host, user, password = [extra[k] for k in ['smtphost', 'user', 'password']]
    org_id = cherrypy.session['org_id']
    with model.sessionScope():
        msg_template = model.Organisation[org_id].mail_body
    smtp_c = smtp.mkclient(host, user, password)
    mailfrom = extra['mailfrom']
    start = extra['period_start'].strftime('%d-%m-%Y')
    end = extra['period_end'].strftime('%d-%m-%Y')
    year = extra['period_start'].strftime('%Y')
    usersfname = USERS_FILE.format(config.opsdir, org_id)

    def sendSingleMail(to_adres, name, fname):
        if config.testmode():
            to_adres = 'evert.vandewaal@axians.com'
        md_msg = msg_template % {'voornaam': name, 'jaar': year, 'van': start, 'tot': end}
        msg = constructMail(md_msg, fname, To=to_adres, From=mailfrom,
                            Subject='Giftenoverzicht',
                            **{'Reply-To': mailfrom})

        # smtp_c.send_message(msg)
        smtp_c.sendmail(mailfrom, to_adres, bytes(msg))
        logging.info('Sent email to %s' % to_adres)

    if 'mailto' in extra:
        # Send a single overview to a specific person
        sendSingleMail(extra['mailto'], extra['name'], extra['file'])
    else:
        users = json.loads(open(usersfname, 'r').read())
        for user in users:
            fname = pdfName(org_id, user['Name'], user['Code'])
            mailto = user['Email']
            if not mailto or not '@' in mailto:
                # Skip this user: the email address is not set
                continue
            if not os.path.exists(fname):
                continue
            sendSingleMail(mailto, user['Name'], fname)

    raise cherrypy.HTTPRedirect("/process")


def formattedPage(*args, **kwargs):
    phase = Overzichten.getState() or 1
    texts = ['Stap 1: Periode kiezen',
             'Stap 2: Data ophalen',
             'Stap 3: PDFs genereren',
             'Stap 4: Emails versturen']

    buttons = [Button(txt, style='width:100%',
                      btn_type='primary' if phase == i + 1 else 'info',
                      target='/restart?state=%i' % (i + 1)) for i, txt in enumerate(texts)]

    frame = [Div(Div(Div(Title('Overzicht Generator'), klasse='col-md-9'),
                     Div("Hello, %s" % cherrypy.session.get('username', 'Stranger'),
                         '<br>',
                         Link('/logout', 'Logout'), klasse='col-md-3'),
                     klasse='row'), klasse='container-fluid'),
             Div(Div(
                 Div(*buttons, klasse='col-md-3', name='navbar'),
                 Div(*args, klasse='col-md-9'),
                 klasse='row'),
                 klasse='container-fluid')]
    refresh = 2 if phase in [SystemStates.LoadingData, SystemStates.GeneratingPDF] else None
    return Page(*frame, refresh=refresh, **kwargs)


def adminPage(*args, **kwargs):
    phase = Overzichten.getState() or 1
    texts = [('Organisaties', '/organisaties'),
             ('Gebruikers', '/gebruikers'),
             ('Smtp Instellingen', '/smtp_details'),
             ('Testen', '/testing')
             ]

    buttons = [Button(txt, style='width:100%',
                      btn_type='info',
                      target=url) for txt, url in texts]

    frame = [Div(Div(Div(Title('Overzicht Generator'), klasse='col-md-9'),
                     Div("Hello, %s" % cherrypy.session.get('username', 'Stranger'),
                         '<br>',
                         Link('/logout', 'Logout'), klasse='col-md-3'),
                     klasse='row'), klasse='container-fluid'),
             Div(Div(
                 Div(*buttons, klasse='col-md-3'),
                 Div(*args, klasse='col-md-9'),
                 klasse='row'),
                 klasse='container-fluid')]

    return Page(*frame, **kwargs)


def handle_login(**kwargs):
    def check(kwargs):
        """ Check the credentials of a proposed user.
        """
        if not (kwargs[UNAME_FIELD_NAME] and kwargs[PWD_FIELD_NAME]):
            return kwargs, {UNAME_FIELD_NAME: 'Zowel naam als wachtwoord invullen!'}
        with model.sessionScope():
            user = model.User.get(name=kwargs[UNAME_FIELD_NAME])
            if user:
                if model.checkpasswd(kwargs[PWD_FIELD_NAME], user.password):
                    return kwargs, {}
        return kwargs, {UNAME_FIELD_NAME: 'Fout in gebruikersnaam of wachtwoord'}

    def success(**kwargs):
        """ The user was authenticated. Update the session to reflect this.
        """
        with model.sessionScope():
            user = model.User.get(name=kwargs[UNAME_FIELD_NAME])
            cherrypy.session['user_id'] = user.id
            cherrypy.session['username'] = user.name
            cherrypy.session['role'] = user.role
            church = user.church
            if church:
                cherrypy.session['org_id'] = church.id

    # Prepare a simple login form with functions to authenticate and set the session
    org_arg = kwargs if cherrypy.request.method == 'GET' else kwargs.get('org_arg', {})

    form = SimpleForm(Hidden('org_arg'),
                      String(UNAME_FIELD_NAME, 'Gebruikersnaam'),
                      form_input(PWD_FIELD_NAME, 'Wachtwoord', 'password'),
                      validator=check,
                      success=success,
                      defaults={'org_arg': org_arg})
    return Page(Title('Login voor de overzichtgenerator'), form)


smtp_key = 'smtp_%s'

class Worker(threading.Thread):
    workers = {}

    def __init__(self, org_id, *args, **kwargs):
        if org_id in Worker.workers:
            logging.error('There is already a worker running for organisation %s' % org_id)
            return
        threading.Thread.__init__(self)
        Worker.workers[org_id] = self
        self.state = None
        with model.sessionScope():
            org = model.Organisation[org_id]
            self.state = org.status
        self.period_start = org.period_start
        self.period_end = org.period_end
        self.access_token = cherrypy.session['token']
        self.org_id = org_id
        self.ufname = USERS_FILE.format(config.opsdir, org_id)
        self.tfname = TRANSACTIONS_FILE.format(config.opsdir, org_id)
        self.afname = ACCOUNTS_FILE.format(config.opsdir, org_id)
        self.start()

    @staticmethod
    def setState(org_id, state):
        if org_id not in Worker.workers:
            return
        Worker.workers[org_id].state = state
        with model.sessionScope():
            model.Organisation[org_id].status = state

    @staticmethod
    def getState(org_id):
        if org_id in Worker.workers:
            return Worker.workers[org_id].state
        return 0

    @model.sessionScope
    def run(self):
        ''' Load the transactions and users from Exact, and
            store them in JSON files.
        '''
        try:
            org = model.Organisation[self.org_id]
            exact_division = org.exact_division

            if self.getState(self.org_id) == SystemStates.LoadingData:
                try:
                    # Load the users
                    if config.testmode():
                        time.sleep(5)
                        with open(self.ufname) as f:
                            users = json.load(f)
                        with open(self.tfname) as f:
                            transactions = json.load(f)
                        with open(self.afname) as f:
                            accounts = json.load()
                    else:
                        logging.info('Reading data from exact')
                        users = getUsers(exact_division, self.access_token)
                        with open(self.ufname, 'w') as out:
                            out.write(json.dumps(users))
                        logging.info('Read user data')
                        # Load the transactions
                        transactions = getTransactions(exact_division, self.access_token,
                                                       self.period_start, self.period_end)
                        with open(self.tfname, 'w') as out:
                            out.write(json.dumps(transactions))
                        accounts = getAccounts(exact_division, self.access_token)
                        with open(self.afname, 'w') as out:
                            out.write(json.dumps(accounts))
                        logging.info('Read transaction data for organisation %s' % self.org_id)
                        logging.info('There are %s transactions and %s users' % (
                        len(transactions), len(users)))
                    self.setState(self.org_id, SystemStates.GeneratingPDF)
                except:
                    logging.exception('Exception while loading data from exact')
                    return
            else:
                users = json.load(open(self.ufname))
                transactions = json.load(open(self.tfname))
                accounts = json.load(open(self.afname))

            if self.getState(self.org_id) == SystemStates.GeneratingPDF:
                try:
                    # Now generate the overviews as PDF's.
                    org_dict = org.to_dict(with_lazy=True)
                    # Add information about the accounts
                    org_dict['account_descriptions'] = {a['Code']: a['Description'] for a in
                                                        accounts}
                    generate_pdfs(org_dict, users, transactions)
                    self.setState(self.org_id, SystemStates.PDFCreated)
                except:
                    logging.exception('Exception while generating PDFs')
                    return
        finally:
            # Cleanup
            del Worker.workers[self.org_id]


def check_token(func):
    def doIt(*args, **kwargs):
        if 'token' not in cherrypy.session:
            raise cherrypy.HTTPRedirect('/')
        return func(*args, **kwargs)

    return doIt


class SmtpDetailsData:
    table = SmtpDetails
    name = 'SmtpDetails'

    def __init__(self, keychain):
        self.keychain = keychain

    @contextmanager
    def scope(self):
        yield

    def column_details(self):
        details = {
        f.name: ColumnDetails(f.name, False, f.type, False, None, False, True, None, f.default)
            for f in fields(SmtpDetails)}
        return details

    def query(self, rid=None):
        if rid:
            details = self.keychain.get(smtp_key % rid, None)
            if details:
                return SmtpDetails(**details)
            return None
        return [SmtpDetails(**v) for k, v in self.keychain.items() if k.startswith('smtp_')]

    def add(self, **kwargs):
        rid = kwargs.get('id', None)
        if not rid:
            raise RuntimeError('Can not add new records this way')
        self.keychain[smtp_key % rid] = kwargs

    def update(self, rid, details):
        if isinstance(details, SmtpDetailsData.table):
            details = asdict(details)
        self.keychain[smtp_key % rid] = details

    def delete(self, rid):
        key = smtp_key % rid
        if key in self.keychain:
            del self.keychain[key]




class Overzichten:
    acm = ACM({}, handle_login)
    keychain = KeyRing('%s/data.bin'%config.opsdir, 'Giften Overzicht datafile')
    smtp_data = SmtpDetailsData(keychain)

    @staticmethod
    def getState():
        org_id = cherrypy.session.get('org_id', 0)
        if org_id:
            with model.sessionScope():
                return SystemStates(model.Organisation[org_id].status)
        return 0

    @staticmethod
    def setState(state):
        org_id = cherrypy.session.get('org_id', 0)
        if org_id:
            Worker.setState(org_id, state)
            with model.sessionScope():
                model.Organisation[org_id].status = state

    @cherrypy.expose
    @authenticateExact
    def index(self, **kwargs):
        # Everytime a person is authenticated through Exact, they go through here.
        # Set the Exact token in the session
        cherrypy.session['token'] = kwargs['token']
        # Also set a default userid and role for the administrative part of the website
        if not cherrypy.session.get('user_id', False):
            cherrypy.session['user_id'] = 'exact'
        if not cherrypy.session.get('role'):
            cherrypy.session['role'] = 'Admin'
        if 'org_id' in cherrypy.session:
            raise cherrypy.HTTPRedirect('/process')
        else:
            raise cherrypy.HTTPRedirect('/select_division')

    def getOptions(self):
        with model.sessionScope():
            organisations = [o for o in model.Organisation.select()]
            divisions = [o.exact_division for o in organisations]
            authorized = checkAuthorization(divisions, cherrypy.session['token'])
            filtered_div = [o for o in organisations if o.exact_division in authorized]
            options = [(o.id, o.name) for o in filtered_div]
            return options

    @cherrypy.expose
    @check_token
    def select_division(self, **kwargs):
        def onChoice(**kwargs):
            cherrypy.session['org_id'] = int(kwargs['administratie'])
            raise cherrypy.HTTPRedirect('/process')

        return Page(Title('Overzicht Generator'),
                    SimpleForm(Selection('administratie', self.getOptions, 'Kies een administratie'),
                               defaults=kwargs,
                               success=onChoice))

    @cherrypy.expose
    @check_token
    def process(self, **kwargs):
        org_id = cherrypy.session['org_id']
        with model.sessionScope():
            org = model.Organisation[org_id]
        handlers = {SystemStates.Start: self.periode,
                    SystemStates.LoadingData: self.loading,
                    SystemStates.GeneratingPDF: self.generating,
                    SystemStates.PDFCreated: self.present_overzicht}
        # Use the state suggested by the database
        state = self.getState() or 1
        # Check if the state of the file system corresponds
        if not os.path.exists(PDF_DIR.format(config.opsdir, org_id)):
            state = min(state, SystemStates.GeneratingPDF)
        if not os.path.exists(USERS_FILE.format(config.opsdir, org_id)) or not os.path.exists(
                        TRANSACTIONS_FILE.format(config.opsdir, org_id)):
            state = min(state, SystemStates.LoadingData)
        if org.period_start is None or org.period_end is None:
            state = min(state, SystemStates.Start)
        if state != self.getState():
            self.setState(state)
        self.check_worker(state)
        handler = handlers[state]
        return formattedPage(*handler(**kwargs))

    def periode(self, **kwargs):
        # Clear the directory containing the PDF files
        org_id = cherrypy.session['org_id']
        pdfdir = PDF_DIR.format(config.opsdir, org_id)
        if os.path.exists(pdfdir):
            shutil.rmtree(pdfdir)
        os.mkdir(pdfdir)
        self.setState(SystemStates.Start)

        # Present a form to generate a new overview
        now = datetime.datetime.now()
        defaults = {'year': now.year,
                    'from': 1,
                    'until': now.month,
                    'token': cherrypy.session['token']}
        form = SimpleForm(Hidden('token'),
                          Integer('year', 'Jaar'),
                          Integer('from', 'Vanaf'),
                          Integer('until', 'Tot en met'),
                          validator=periode_validator(),
                          defaults=defaults,
                          success=self.period_known
                          )
        return Title('Kies de periode'), form

    def period_known(self, **kwargs):
        ''' Function called when the results of a submitted form check out '''
        # DONT TRUST THE ARGUMENTS!
        results, errors = periode_validator()(kwargs)
        if errors:
            # This is fishy: args should be checked by the form handler
            # so don't give more information then we need to
            raise cherrypy.HTTPError(400, 'Invalid Request')
        year, first, last = [results[k] for k in ['year', 'from', 'until']]
        start = datetime.datetime(year, first, 1)
        end = datetime.datetime(year, last, calendar.monthrange(2016, last)[1], 23, 59, 59)
        token = kwargs['token']
        # Start a thread to load the actual data from exact
        with model.sessionScope():
            org = model.Organisation[cherrypy.session['org_id']]
            org.period_start = start
            org.status = SystemStates.LoadingData
            org.period_end = end
        _ = Worker(org.id)

    def loading(self, **kwargs):
        return Title('Loading data from Exact Online'), Div(
            'Het systeem is gegevens aan het ophalen uit Exact; even geduld a.u.b.')

    def generating(self, **kwargs):
        return Title('PDF files genereren'), Div(
            'Het systeem is PDF files aan het genereren; even geduld a.u.b.')

    def present_overzicht(self):
        org_id = cherrypy.session['org_id']
        with model.sessionScope():
            org = model.Organisation[org_id].to_dict(with_lazy=True)
            org['account_descriptions'] = {k: '' for k in org['gift_accounts'].split()}

        def data_gen(d):
            # Order by rid
            d = sorted(d, key=lambda x: x[0])
            for rid, naam, email, totaal, _ in d:
                totaal = amount2Str(totaal)
                email = email if email else '-'
                pdf = pdfUrl(naam, rid)[1:]  # Remove the prefix '.'
                pdf_internal = pdfName(org_id, naam, rid)
                yield rid, naam, email, totaal, pdf, pdf_internal

        t = json.loads(open(TRANSACTIONS_FILE.format(config.opsdir, org_id)).read(), parse_float=Decimal)
        u = json.loads(open(USERS_FILE.format(config.opsdir, org_id)).read())
        data = generate_overviews(org, u, t)

        return overzicht(data_gen(data))

    @cherrypy.expose
    @check_token
    def all(self, fname):
        p = os.path.join(PDF_DIR.format(config.opsdir, cherrypy.session['org_id']), fname)
        print('REQUESTED', fname, os.path.exists(p))
        # Always add a delay to hinder brute-force attacks.
        # It is useless to only add it when an error occurred, then they just wait 0.1 second
        # and interpret lack of response as failure.
        time.sleep(3)
        return serve_file(os.path.abspath(p), "application/x-pdf", fname)


    @cherrypy.expose
    def logout(self):
        cherrypy.session.clear()
        raise cherrypy.HTTPRedirect('/')

    def check_worker(self, state):
        if state in [SystemStates.LoadingData, SystemStates.GeneratingPDF]:
            if not cherrypy.session['org_id'] in Worker.workers:
                _ = Worker(cherrypy.session['org_id'])

    @cherrypy.expose
    @check_token
    def restart(self, state=SystemStates.Start.value):
        self.setState(state)
        self.check_worker(state)
        raise cherrypy.HTTPRedirect('/process')

    @cherrypy.expose
    @check_token
    def versturen(self, **kwargs):
        with model.sessionScope():
            sid = cherrypy.session['org_id']
            org = model.Organisation[sid]
            params = keychain[smtp_key % sid]
            params['period_start'] = org.period_start
            params['period_end'] = org.period_end
            params['mailfrom'] = org.mailfrom
        params.update(kwargs)

        return verstuur_overzicht(**params)


    ### The administration pages

    crud_acm = ACM(
        {'view': ['Admin', 'User'], 'index': ['Admin'], 'edit': ['Admin'], 'delete': ['Admin']},
        handle_login)


    test_report_name = 'testoverzicht'

    def check_testmail(self, **kwargs):
        p = os.path.join(PDF_DIR.format(config.opsdir, 0, self.test_report_name))
        if not os.path.exists(p):
            return Verify


    def send_testmail(self):
        pass


    @cherrypy.expose
    @crud_acm
    def show_testtemplate(self, *args):
        fname = pdfName('0', 'Puk, Pietje', '              1661')
        print('Trying', fname)
        return serve_file(os.path.abspath(fname), "application/x-pdf", 'testreport.pdf')

    def render_template(self, org_id):
        with model.sessionScope():
            org = model.Organisation[org_id].to_dict(with_lazy=True)
        home = os.path.join(os.path.dirname(__file__), '../..')
        org['id'] = 0
        org['gift_accounts'] = '8000 8100'

        transactions = json.load(open(os.path.join(home, 'test/giftenoverzicht_tests/1.transactions.json')))
        users = json.load(open(os.path.join(home, 'test/giftenoverzicht_tests/1.users.json')))
        generate_pdfs(org, users, transactions)
        raise cherrypy.HTTPRedirect('/show_testtemplate')


    def getOrganisations(self):
        with model.sessionScope():
            orgs = model.Organisation.select()
            return [(o.id, o.name) for o in orgs]



    @cherrypy.expose
    @crud_acm
    def generate_testreport(self, **kwargs):
        if 'org_id' in cherrypy.session:
            orgid = Hidden('org_id')
        else:
            orgid = Selection('org_id', self.getOrganisations, 'Kies een administratie')
        return adminPage(SimpleForm(orgid,
                                    submit='Genereer Testdocument',
                                    success=self.render_template
                                    )
                         )

    @cherrypy.expose
    @crud_acm
    def testing(self, **kwargs):
        return adminPage(Button('Genereer een testrapport', 'generate_testreport'))



    organisaties = generateCrud(DataInterface(model.Organisation), adminPage, acm=crud_acm,
                                index_show=['id', 'name', 'description'],
                                hidden=['period_start', 'period_end', 'status']
                                )

    gebruikers = generateCrud(DataInterface(model.User), adminPage, acm=crud_acm,
                              index_show=['id', 'name', 'fullname', 'role'])

    smtp_details = generateCrud(smtp_data, adminPage, acm=crud_acm,
                                index_show=['id', 'name', 'mailfrom'], hidden='id')

    def new_index(wrapped):
        """ Function for editing the SMTP details """
        @cherrypy.expose
        def doit(*args, **kwargs):
            # First check that records exist for all organisations
            with sessionScope:
                for organisation in model.Organisation.select():
                    if Overzichten.smtp_data.query(organisation.id) is None:
                        details = SmtpDetails(
                            id = organisation.id,
                            name = organisation.name,
                            smtphost='',
                            user='',
                            password=''
                        )
                        Overzichten.smtp_data.add(**asdict(details))
            return wrapped(*args, **kwargs)
        return doit
    smtp_details.index = new_index(smtp_details.index)


def run(static_dir=None):
    model.openDb('sqlite://%s/overzichtgen.db' % config.opsdir)

    # Ensure there is a 'test' user with password 'testingtesting'
    # This should be changed immediatly after deployment!
    # When deploying the giftenoverzicht app, remember to delete this user!
    with sessionScope():
        if orm.count(u for u in model.User) == 0:
            test_user = model.User(name='test', fullname='test user',
                                   password=password2str('testingtesting'),
                                   role='Admin',
                                   email='pietje.puk@sesamstraat.nl')

    # cherrypy.log.access_log.propagate = False
    logging.getLogger('cherrypy_error').setLevel(logging.ERROR)
    conf = config.getConfig('server')

    if not conf and config.testmode():
        projdir = os.path.dirname(__file__)
        conf = {'global': {
            "tools.sessions.on": True
               }, '/': {
            "tools.staticdir.root": projdir,
            "tools.staticdir.on": True,
            "tools.staticdir.dir": './public'
        }
        }

    cherrypy.quickstart(Overzichten(), '/', conf)


if __name__ == '__main__':
    # static_dir = os.path.abspath(os.getcwd() + '/static/')
    static_dir = os.path.abspath(os.getcwd())
    run(static_dir)
