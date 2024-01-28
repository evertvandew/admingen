
import os.path
import traceback
from datetime import datetime
import flask
import json
import random
from dataclasses import asdict
from admingen.data import serialiseDataclass, checkpasswd
import data_model
import logging
from admingen.htmltools.acm import ACM
import secrets
import matplotlib
import subprocess
import sys

# Force matplotlib to not use any Xwindows backend.
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from math import pi, sin, cos
from admingen.clients import smtp
from admingen import config


MAX_ANSWER = 5

RESOURCE_DIR = 'resources'

RENDER_WORD = 'admingen/bin/render_word_template'


LOGO_NAME = 'logo_company'

acm = ACM(role_hierarchy=' '.join(i.name for i in data_model.UserRole), data_fields='bedrijf,klant', project_name='questionnaire')

###############################################################################
## Additional security:
##
# This is a multi-user website. The users are separated through the 'company'
# field. All other database records have this field, and we check that only
# coaches from that same company can view or modify those records.
# Some records are also private. We ensure that only that user, or a coach from
# the relevant company, can view or modify those records.

def create_filter_company(*details):
    """ We need to limit the rights of a coach:
        they always create objects for their own company.
    """
    if flask.request.cookies.get(acm.rolename_name, '') == 'coach':
        details['bedrijf'] = flask.request.cookies.get(acm.company_name, '')
    return details

def read_filter_company(records):
    """ We need to filter the users for a coach:
        he can only see customers for their own company.
    """
    company = int(flask.request.cookies.get(acm.company_name, ''))
    records = [u for u in records if u.company == company]
    return records

def update_filter_company(*details):
    """ A coach user is never allowed to change the company of a user """
    if 'company' in details:
        del details['bedrijf']

def delete_check_company(*details):
    """ A coach can only delete objects for their own company.
        This check returns TRUE if it is OK to delete the record.
    """
    company = int(flask.request.cookies.get(acm.company_name, ''))
    if 'bedrijf' in details:
        return int(details['bedrijf']) == company
    # This record is not protected for a specific company
    return True

def read_filter_user(records):
    """ We need to filter these records also on user:
        these are things a user can see.
    """
    if flask.request.cookies.get(acm.rolename_name, '') == 'customer':
        user = int(flask.request.cookies.get(acm.userid_name, ''))
        records = [u for u in records if int(u.klant) == user]
    return records


default_msg = """Beste {user.vollenaam},

Hierbij ontvang je de uitnodiging voor het invullen van de "{questionair.omschrijving}" persoonlijkheidstest. 
Het maken van de test kost gemiddeld 30 minuten, neem er rustig zoveel tijd voor als je nodig hebt, 
maar denk niet te lang na over je antwoord. De instructies en de vragen volgen als je op onderstaande link klikt:

[{url}]({url}).

Veel plezier met het invullen van de persoonlijkheidstest!

Hartelijke groet,

{sender.vollenaam}
"""

def count(gen):
    if type(gen) in [list, set, str, bytearray, dict]:
        return len(gen)
    c = 0
    for c, _ in enumerate(gen):
        pass
    return c+1


def check_invitation_acm(db):
    invitation_id = int(flask.request.values['invitation'])
    # Ensure the user is authorized to view this...
    # Because of the ACM rules for this page, we are sure the user is authenticated.
    try:
        invitation = db.get(data_model.Uitnodiging, invitation_id)
    except:
        return "Not Found", 404

    user_id = int(flask.request.cookies.get(acm.userid_name, ''))
    role = flask.request.cookies.get(acm.rolename_name, '')
    company = int(flask.request.cookies.get(acm.company_name, ''))
    authorized = invitation.klant == user_id
    authorized = authorized or (role == 'editor' and company == invitation.bedrijf)
    authorized = authorized or (role == 'administrator')
    if not authorized:
        return "Not authorized", 403
    return invitation


def store_template(questionair):
    if not questionair.rapport_template:
        return None
    template_name = f'{RESOURCE_DIR}/{questionair.rapport_template.fname}'
    with open(template_name, 'wb') as out:
        out.write(questionair.rapport_template.data)
    return template_name

def calculate_scores(db, company_id, invitation):
    # Get the questions, joined to answers and categories.
    questions = db.query(data_model.Question,
                         filter=lambda r: r.questionaire == invitation.questionaire,
                         join=(data_model.Antwoord, lambda a, b: b.vraag == a.id and b.uitnodiging == invitation.id),
                         )
    categories = db.query(data_model.Categorie,
                          filter=lambda r: r.questionaire == invitation.questionaire)

    norms = {c.id: count(q for q in questions if q.categorie == c.id) * 5 for c in categories}

    bins = {c.id: 0 for c in categories}
    for q in questions:
        if q.telt_negatief:
            bins[q.categorie] += (MAX_ANSWER - q.Antwoord.antwoord)
        else:
            bins[q.categorie] += q.Antwoord.antwoord

    result = {'categories': {c.id: asdict(c) for c in categories},
              'scores': {c.id: float(bins[c.id]) / norms[c.id] * 100 for c in categories}
              }
    return result


def create_report(invitation, klant, coach, questionair, company, fname, scores):
    # Start a background process for handling word documents
    # Save the template to file.
    template_name = store_template(questionair)

    plotfile =  os.path.abspath(f'{RESOURCE_DIR}/score_plot_{invitation.id}.svg')
    logo = f'img({RESOURCE_DIR}/logo_{company.id})'
    # Ensure the company logo is stored on file.
    company.logo = logo if os.path.exists(logo) else ''
    scores_summary = {scores['categories'][i]['naam']: int(scores['scores'][i]+0.5) for i in scores['categories'].keys()}
    context = dict(
        uitnodiging = invitation,
        klant = klant,
        coach = coach,
        questionaire = questionair,
        company = company,
        scoreplot = f'img({plotfile})',
        scores = scores_summary
    )
    arguments = serialiseDataclass(context).encode('utf8')
    if config.testmode():
        with open('/tmp/debug.txt', 'wb') as out:
            out.write(arguments)

    # Ensure the file lives in the file space.
    if not os.path.exists(template_name):
        with open(template_name, 'wb') as t:
            t.write(questionair.rapport_template.data)
    #arguments = io.BytesIO(arguments.encode('utf8'))
    result = subprocess.run([RENDER_WORD, template_name, fname], input=arguments)
    if result.returncode:
        logging.error("Could not render Word template: %s"%result.stderr)


def reorder_questionair(db, qid):
    questions = db.query(data_model.Question, filter=lambda r: r.questionaire == qid)
    indices = list(range(len(questions)))
    random.shuffle(indices)
    for o, q in zip(indices, questions):
        q.order = o
        db.update(q)


default_colors = '#3081B9 #FF9437 #33A333 #D83939 #9E76C3 #946258 #E378C2 #808080 #BDBE28 #1BBFCF'.split()


def create_sector_chart(values, labels, colors=None, outstream=sys.stdout):
    outstream.write('<svg width="15cm" height="15cm" viewBox="-20 -20 140 140" xmlns="http://www.w3.org/2000/svg">')
    font_size = 4.5
    r = 50
    nr_sectors = len(values)
    sector_angle = 2 * pi / nr_sectors
    sector_angle_deg = 360 / nr_sectors
    coordinates = [(r * sin(i * sector_angle), r * cos(i * sector_angle)) for i in range(nr_sectors)]
    colors = colors or list(default_colors.values())
    colors = [c or default_colors[i % len(default_colors)] for i, c in enumerate(colors)]

    # Write the sectors to the stream
    for i, (value, color) in enumerate(zip(values, colors)):
        s = f'''<path fill="{color}" stroke="none"
        d="M {r} {r}
           L {r + value / 100 * coordinates[i][0]} {r - value / 100 * coordinates[i][1]}
           A {r} {r} 0 0 1 {r + value / 100 * coordinates[(i + 1) % nr_sectors][0]} {r - value / 100 * coordinates[(i + 1) % nr_sectors][1]}
           L {r} {r}
        " />
'''
        outstream.write(s)

    # Write the reference lines
    if True:
        for coods in coordinates:
            s = f'<line x1="{r}" y1="{r}" x2="{r + coods[0]}" y2="{r - coods[1]}" stroke="black" stroke-width="0.1pt"/>\n'
            outstream.write(s)

    # Write the labels
    if True:
        for i, label in enumerate(labels[:nr_sectors]):
            s = f'<text x="{r}" y="{-2.2 * font_size}" transform="rotate({0.5 * sector_angle_deg + sector_angle_deg * i}, {r}, {r})" text-anchor="middle" font-size="{font_size}pt" >{label}</text>\n'
            outstream.write(s)

    # Write the numerical values under the labels.
    if True:
        for i, value in enumerate(values[:nr_sectors]):
            s = f'<text x="{r}" y="{-0.85 * font_size}" transform="rotate({0.5 * sector_angle_deg + sector_angle_deg * i}, {r}, {r})" text-anchor="middle" font-size="{0.75 * font_size}pt" >{int(value + 0.5)}%</text>\n'
            outstream.write(s)

    outstream.write('</svg>')

def create_polar_plot(values, labels, fname):
    x_values = [i * 2 * pi / len(labels) for i in range(len(labels))]

    # To create a polar plot, the first value needs to be the same as the last one.
    plt.polar(x_values + [0], values + [values[0]])
    plt.xticks(x_values, labels)
    ax = plt.gca()
    ax.set_rlim(0, 100)

    # Upload it as a file, in a directory that is not accessible.
    plt.savefig(fname)


def handle_new_questionair(db, file, company):
    """ Handle a new questionair, uploaded as a CSV file. """
    filename = file.filename

    # Some checking:
    if not filename or '..' in filename or filename[0] == '/':
        return "Incorrect filename", 400

    # Load the file and extract the questions
    data = file.stream.read()
    lines = [l.strip() for l in data.split(b'\n') if l.strip()]
    if len(lines) < 2:
        return "No questions found", 400

    # Determine the delimitor: either a comma or a semi-colon.
    delimiter = None
    for d in b'\t,;':
        count = [l.count(d) for l in lines]
        average = sum(count) / len(count)
        if 1 <= average <= 3:
            delimiter = d
    if not delimiter:
        return "No delimiter found", 400

    all_parts = [l.split(bytes([delimiter])) for l in lines]

    # All lines must have at least two parts.
    if any(True for parts in all_parts if len(parts) < 2):
        return "Empty lines or lines without category found", 400

    # Ensure all lines have three columns
    for parts in all_parts:
        if len(parts) == 2:
            parts.append('')

    # Check if the first line is a header
    # This is seen by the third colomn having more than 1 character
    if len(all_parts[0][2]) > 1:
        all_parts = all_parts[1:]

    # Check all remaining third colomns have either 0 or 1 characters
    if [a for a in all_parts if len(a[2]) > 1]:
        return "Got question(s) with more than one character in column 3", 400

    # Determine which categories are there by collecting them in a set.
    categories = set(p[1] for p in all_parts)
    categories = list(categories)

    # We need to have the id's for the questionaire and categories to create related objects.
    q = db.add(data_model.Questionair(bedrijf=company, naam=filename))
    cats = [db.add(data_model.Categorie(questionaire=q.id,
                                        bedrijf=company,
                                        naam=cat.decode('utf8'))) for cat in categories]
    cats = dict(zip(categories, cats))

    # Ignore lines without a question
    all_parts = [a for a in all_parts if a[0]]

    # Create the questions in the database
    # Also generate a random order for presenting these questions.
    indices = list(i + 1 for i in range(len(all_parts)))
    random.shuffle(indices)

    for order, parts in zip(indices, all_parts):
        question = parts[0].decode('utf8')
        categorie = parts[1]
        db.add(data_model.Question(questionaire=q.id,
                                   vraag=question,
                                   categorie=cats[categorie].id,
                                   telt_negatief=bool(parts[2] and parts[2] in b'*-nN'),
                                   bedrijf=company,
                                   order=order))

    # Done
    return 'OK', 201


def handle_new_invite(db, user_id, questionair_id, company_id, sender_id, smtp_config):
    # Get both the user and the questionair, and check authorization
    user = db.get(data_model.User, user_id)
    sender = db.get(data_model.User, sender_id)
    questionair = db.get(data_model.Questionair, questionair_id)
    if user.bedrijf != questionair.bedrijf or user.bedrijf != company_id:
        return "Not Authorized", 401

    # Now generate the invitation object
    uitn = db.add(data_model.Uitnodiging(klant=user_id,
                                         questionaire=questionair_id,
                                         uitnodiging=datetime.now(),
                                         ingevuld=None,
                                         bedrijf=user.bedrijf))

    # Generate a "secret" link for filling in the uitnodiging.
    ll = None
    while not ll:
        try:
            # Add the long link bypassing the ACM mechanisms.
            if db.has_acm:
                raw_db_class = db.get_raw_db()
            else:
                raw_db_class = db
            ll = raw_db_class.add(data_model.LongLink(
                set_uid=user_id,
                uitnodiging=uitn.id,
                id=secrets.token_urlsafe(50),
            ))
        except RuntimeError as e:
            # This _can_ fail, in rare circumstances, if there is a collision in the ID.
            print(traceback.format_exc())
            pass

    # Generate an email and send it
    if smtp_config:
        msg = default_msg.format(user=user,
                                 questionair=questionair,
                                 uitnodiging=uitn,
                                 sender=sender,
                                 url=f'https://questionaires.nl/query/invitation/{ll.id}')
        smtp_c = smtp.mkclient(smtp_config['host'], smtp_config['user'], smtp_config['password'])
        mailfrom = sender.email

        headers = {'To': user.email,
                   'From': f"{user.login}@questionaires.nl",
                   'Reply-To': user.email,
                   'Subject': 'Uitnodiging om questionaire in te vullen',
                   'Reply - To': mailfrom
                   }
        html_msg = smtp.constructMailMd(msg, **headers)

        smtp_c.sendmail(mailfrom, user.email, bytes(html_msg))
    return "OK", 200


def handle_get_questions(db, invitation_id, user_id, page_parameter):
    # Check if the invitation points to a valid record
    try:
        invitation_id = int(invitation_id)
        invitation = db.get(data_model.Uitnodiging, invitation_id)
    except:
        logging.exception('Exception in get_questions')
        return "Error in request", 400

    # Check the user is authorized to access this questionair
    user_id = int(user_id)
    if user_id != invitation.klant:
        return "Not authorized", 401

    # Determine what question was the last one to be answered.
    # "When in doubt, use brute force"
    questions = db.query(data_model.Question, filter=lambda rec: rec.questionaire == invitation.questionaire,
                         join=(
                         data_model.Antwoord, lambda r1, r2: r2.vraag == r1.id and r2.uitnodiging == invitation.id))
    questions.sort(key=lambda r: r.order or 0)
    nr_questions = len(questions)
    open_questions = [q for q in questions if q.Antwoord is None]
    nr_open_questions = len(open_questions)
    nr_answered_questions = nr_questions - nr_open_questions

    # Signal the questionaire as filled in.
    if not nr_open_questions:
        db.update(data_model.Uitnodiging, {'id': invitation_id, 'ingevuld': datetime.now()})

    # Handle the paging.
    current_page = nr_answered_questions // 10

    page = int(page_parameter) if page_parameter.isnumeric() else current_page
    nr_pages = ((nr_questions - 1) // 10) + 1
    page = min([page, nr_pages - 1])
    is_final = page >= nr_pages - 1
    records = questions[10 * page:10 * (page + 1)]

    # Return at most 10 open questions
    # Follow the regular protocol for paged lists
    result = {
        'records': records,
        'nr_pages': ((nr_questions - 1) // 10) + 1,
        'current_page': page,
        'remaining_pages': nr_open_questions // 10,
        'is_final_page': is_final,
        'is_done': nr_open_questions == 0,
        'is_closed': invitation.ingevuld
    }
    return result


def handle_submit_answers(db, user_id, invitation_id, request_values):
    # Check the submitter is authorized
    user_id = int(user_id)
    invitation_id = int(invitation_id)
    invitation = db.get(data_model.Uitnodiging, invitation_id)
    if int(invitation.klant) != user_id:
        return "Not authorized", 401

    # Extract the data from the request
    question_order = [int(i) for i in request_values['questions'].split(',')]
    answers = {}
    for i, qid in enumerate(question_order):
        tag = f'values[{i}][value]'
        answers[qid] = int(request_values[tag])
    ans_ids = {}
    for i, qid in enumerate(question_order):
        tag = f'ansids[{i}][value]'
        ans_ids[qid] = request_values[tag]

    # Store the results in the database
    # For new answers, create one, and update existing answers.
    for qid, ans_id in ans_ids.items():
        value = answers[qid]
        details = dict(klant=user_id,
                       uitnodiging=invitation.id,
                       vraag=qid,
                       antwoord=value,
                       bedrijf=invitation.bedrijf)
        if ans_id.isnumeric():
            details['id'] = int(ans_id)
            db.set(data_model.Antwoord(**details))
        else:
            _id = db.add(data_model.Antwoord(**details))
            print("Created", _id)

    return f"Created {len(question_order)} items", 201


no_smtp_config_msg = '''No SMTP configuration file was found. 
Please create one in %s that contains the following (JSON format):
{
    "host": "<your SMTP host name>",
    "user": "<your SMTP user name>",
    "password": "<your STMP password>"
}
'''


def add_handlers(app, context):
    """ Called by the our web framework to add methods and URL's to the Flask app """
    db = context['databases']['ondervrager']
    smtp_config = None
    conf_file = f'{config.configdir}/smtp.conf'
    if not os.path.exists(conf_file):
        logging.error(no_smtp_config_msg % conf_file)
    else:
        smtp_config = json.load(open(conf_file))

    @app.route(acm.roles('/query/upload_questionair', 'administrator,editor'),
               methods=['POST'])
    def upload_questionair():
        """ Handle an uploaded CSV file detailing the questions for a questionaire. """
        file = flask.request.files['file']

        # Determine which 'company' is associated with the questionaire, from the user ID.
        # Use the session to determine the user so this can not be spoofed.
        user_id = int(flask.request.cookies.get(acm.userid_name, ''))
        user = db.get(data_model.User, user_id)
        company = user.bedrijf

        return handle_new_questionair(db, file, company)

    @app.route(acm.roles('/query/invite_user', 'administrator,editor'), methods=['POST'])
    def invite_user():
        user_id = int(flask.request.form['user'])
        questionair_id = int(flask.request.form['questionair'])
        company = int(flask.request.cookies.get(acm.data_fields[0], ''))
        sender_id = int(flask.request.cookies.get(acm.userid_name, ''))

        return handle_new_invite(db, user_id, questionair_id, company, sender_id, smtp_config)

    @app.route(acm.roles('/query/get_questions', 'administrator,editor,user'))
    def get_questions():
        # Check if the invitation points to a valid record
        invitation_id = flask.request.args.get('invitation', None)
        user_id = flask.request.cookies.get(acm.userid_name, None)
        page_parameter = flask.request.args.get('page', '')

        result = handle_get_questions(db, invitation_id, user_id, page_parameter)

        if isinstance(result, dict):
            result = flask.make_response(serialiseDataclass(result))

        return result

    @app.route(acm.roles('/query/submit_answers', 'administrator,editor,user'), methods=['POST', 'PUT'])
    def submit_answers():
        # Check the submitter is authorized
        user_id = flask.request.cookies.get(acm.userid_name, '')
        invitation_id = flask.request.values.get('invitation', '')
        request_values = flask.request.values

        return handle_submit_answers(db, user_id, invitation_id, request_values)

    @app.route(acm.roles('/query/invitation/<string:id>', 'any'), methods=['GET'])
    def use_invitation(id):
        """ A user is following a long link from an invitation.
            Find the associated user and invitation records, and log the user in,
            but only if that user has no password set.
        """
        try:
            llink = db.get(data_model.LongLink, id)
        except:
            logging.exception('Wrong llink followed?')
            return "No Access", 404

        user = db.get_raw(data_model.User, llink.set_uid)

        # If the user does *not* have a password set, log him/her in.
        res = flask.redirect(f"/present_questions?invitation={llink.uitnodiging}", code=302)
        if not user.password or checkpasswd('', user.password):
            res = acm.accept_login(user, res)

        # Redirect to the page handling the invitation.
        return res

    @app.route(acm.roles('/query/scores', 'administrator,editor,user'), methods=['GET'])
    def get_scores():
        """ Calculate the scores for a specific questionaire. """
        company_id = int(flask.request.cookies.get(acm.company_name, ''))
        invitation_id = int(flask.request.values['invitation'])
        invitation = db.get(data_model.Uitnodiging, invitation_id)
        if int(invitation.bedrijf) != company_id:
            return "Not authorized", 401
        # Check the invitation has not been completed.
        if invitation.ingevuld is None:
            return "Deze questionaire is nog niet ingevuld.", 400

        return calculate_scores(db, company_id, invitation)


    @app.route(acm.roles('/query/polar_plot.svg', 'administrator,editor,user'), methods=['GET'])
    def score_plot():
        """ Calculate and return the plot of the questionair scores """
        if not isinstance(result := check_invitation_acm(db), data_model.Uitnodiging):
            return result
        invitation = result

        fname = f'{RESOURCE_DIR}/score_plot_{invitation.id}.svg'
        png_fname = f'{RESOURCE_DIR}/score_plot_{invitation.id}.png'
        if not os.path.exists(fname):
            # Query the database and get the scores for this questionaire.
            details = get_scores()
            category_ids = sorted(details['categories'].keys())
            # Construct the graph.
            cat_names = [details['categories'][i]['naam'] for i in category_ids]
            cat_colors = [details['categories'][i]['kleur'] for i in category_ids]
            with open(fname, 'w') as out:
                create_sector_chart([details['scores'][i] for i in category_ids],
                                    cat_names, cat_colors, out)

        if flask.request.base_url.endswith('.svg'):
            return flask.send_from_directory(os.path.dirname(fname),
                                             os.path.basename(fname))
        else:
            return "Not Found", 404
            return flask.send_from_directory(directory=os.path.dirname(fname),
                                             filename=os.path.basename(png_fname))

    @app.route(acm.roles('/query/query_report.pdf', 'administrator, editor'))
    @app.route(acm.roles('/query/query_report.raw', 'administrator, editor'))
    def download_report():
        if isinstance(result := check_invitation_acm(db), tuple):
            return result
        invitation: data_model.Questionair = result

        questionair = db.get(data_model.Questionair, invitation.questionaire)
        if not questionair.rapport_template:
            return "Er is geen template ingesteld voor deze questionaire"

        base, ext = os.path.splitext(questionair.rapport_template.fname)
        fname = f'{RESOURCE_DIR}/{base}_{invitation.id}{ext}'
        pdf_fname = f'{RESOURCE_DIR}/{base}_{invitation.id}.pdf'

        if not os.path.exists(pdf_fname):
            klant = db.get(data_model.User, invitation.klant)
            if klant.coach:
                coach = db.get(data_model.User, klant.coach)
            else:
                coach = data_model.User(id=None, login='---', password='', rol=data_model.UserRole.user, email='---', vollenaam="---", coach=None, bedrijf=None)

            company = db.get(data_model.Bedrijf, invitation.bedrijf)
            scores = calculate_scores(db, company.id, invitation)
            create_report(invitation, klant, coach, questionair, company, fname, scores)

        # Present the file as a download.
        if flask.request.base_url.endswith('.pdf'):
            return flask.send_from_directory(os.path.dirname(pdf_fname),
                                             os.path.basename(pdf_fname),
                                             as_attachment=True)
        else:
            return flask.send_from_directory(os.path.dirname(fname),
                                             os.path.basename(fname),
                                             as_attachment=True,
                                             attachment_filename=questionair.rapport_template.fname)

    @app.route(acm.roles('/query/stylesheet.css', 'administrator, editor, user'))
    def custom_stylesheet():
        """ Return the custom stylesheet for the company. """
        default_style = ''
        # If the company has a custom style, return it.
        # First remove any potentially dangerous characters.
        company_id = int(flask.request.cookies.get(acm.company_name, -1))
        style = None
        if company_id:
            company = db.get(data_model.Bedrijf, company_id)
            style = company.style or default_style
            # Do not allow the user to escape XML tags.
            for ch in '<>':
                if ch in style:
                    # Remove the offending characters
                    style = style.replace(ch, '')

            if (style is not None) and (style != company.style):
                company.style = style
                db.update(company)

        style = style or default_style
        res = flask.make_response(style)
        res.headers['Content-Type'] = 'text/css'
        return res



    # Ensure the company logos are also stored in the file system in a location that can be accessed.
    if db:
        @db.define_hook(data_model.Bedrijf, db.actions.post_delete)
        def on_bedrijf_delete(record):
            index = record
            p = f'{RESOURCE_DIR}/{LOGO_NAME}_{index}'
            if os.path.exists(p):
                os.remove(p)
        @db.define_hook(data_model.Bedrijf, db.actions.post_update)
        def on_bedrijf_change(record):
            index = record.id
            if record.logo:
                with open(f'{RESOURCE_DIR}/{LOGO_NAME}_{index}', 'wb') as out:
                    out.write(record.logo.data)

        @db.define_hook(data_model.Question, db.actions.post_add)
        @db.define_hook(data_model.Question, db.actions.post_update)
        def on_question_add(record):
            if not record.order:
                # The questionair must be re-ordered. Do it now.
                reorder_questionair(db, record.questionaire)

    # Also add the handlers for the ACM
    acm.add_handlers(app, context)

if __name__ == '__main__':
    # The default action when run as a script, is to write the ACM information to stdout.
    class FlaskDummy:
        def route(self, *args, **kwargs):
            def doit(func):
                return func
            return doit
    add_handlers(FlaskDummy(), {'databases': {'ondervrager': None}})
    for route, roles in acm.acm_table.items():
        if isinstance(roles, list):
            roles = ','.join(roles)
        print(f'{route}:{roles}')
    for route, roles in acm.parameterized_acm_table.items():
        print(f'{route}/*:{roles}')
