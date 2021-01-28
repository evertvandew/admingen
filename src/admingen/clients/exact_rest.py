import cherrypy
import logging
import urllib
from datetime import datetime
from urllib.parse import urlencode
import json
import threading
import time
from admingen.config import configtype, testmode
import traceback



@configtype
class ExactClientConfig:
    """ Define a singleton object that contains the configuration """
    base = ''
    client_secret = ''
    webhook_secret = ''
    client_id = ''
    redirect_uri = ''

    @property
    def auth_url(self): return self.base + '/oauth2/auth'

    @property
    def token_url(self): return self.base + '/oauth2/token'

    @property
    def transaction_url(self): return self.base + r"/v1/%(division)i/financialtransaction/TransactionLines"

    @property
    def users_url(self): return self.base + r"/v1/%(division)i/crm/Accounts"

    @property
    def accounts_url(self): return self.base + r"/v1/%(division)i/financial/GLAccounts"

    @property
    def btwcodes_url(self): return self.base + r"/v1/%(division)i/financial/VATs"


eoconfig = ExactClientConfig()


def binquote(value):
    """
    We use quote() instead of urlencode() because the Exact Online API
    does not like it when we encode slashes -- in the redirect_uri -- as
    well (which the latter does).
    """
    return urllib.parse.quote(value.encode('utf-8'))


def request(url, token=None, method='GET', params={}, query={}, handle=None, progress=None):
    headers = {}  # {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
        headers['Accept'] = 'application/json'
    data = '&'.join('%s=%s' % i for i in params.items()).encode('utf-8') if params else None

    if query:
        url = '?'.join([url, urlencode(query)])

    result = []
    status = -1
    reason = ''
    part_count = 0
    while True:
        part_count += 1
        if progress:
            progress('part %i' % part_count)
        logging.info('Sending request %s, %s, %s', url, method, data)
        r = urllib.request.Request(url=url, method=method, data=data, headers=headers)
        try:
            response = urllib.request.urlopen(r, capath='/etc/ssl/certs')
        except urllib.error.HTTPError as e:
            with e as f:
                d = f.read()
            logging.error("Error in request: %s, %s", e.code, e.reason, d)
            return

        with response as f:
            d = f.read()
            logging.info('Response status %s (%s)' % (f.status, f.reason))
            logging.debug('Read: %s' % d)
            res = json.loads(d.decode('utf-8'))
            logging.debug('JSON keys: %s' % res.keys())
            if 'd' in res:
                result += res['d']['results']
                if '__next' in res['d']:
                    url = res['d']['__next']
                    continue
                break
            result = res
            status, reason = f.status, f.reason
            break
    if handle:
        handle(status, reason, result)
    return result


def getTransactions(exact_division, token, start: datetime, end: datetime, progress=None):
    start = start.strftime('%Y-%m-%dT%H:%M:%S')  # '2016-01-01T00:00:00'
    end = end.strftime('%Y-%m-%dT%H:%M:%S')
    # url = transaction_url%{'division': LC_division, 'start':start}
    url = "https://start.exactonline.nl/api/v1/%s/financialtransaction/TransactionLines" % exact_division
    options = {'$filter': "Date ge DateTime'%s' and Date le DateTime'%s'" % (start, end),
               '$select': 'AccountCode,AccountName,Date,AmountDC,EntryNumber,GLAccountCode,Description',
               '$inlinecount': 'allpages'}
    transactions = request(url, token, query=options, progress=lambda x: progress('Reading transactions '+x))
    return transactions


def getUsers(exact_division, token, progress=None):
    options = {'$select': 'Code,Name,Email'}
    users = request(eoconfig.users_url % {'division': exact_division}, token, query=options, progress=lambda x: progress('Reading users '+x))
    return users


def getAccounts(exact_division, token, progress=None):
    options = {'$select': 'Code,Description'}
    users = request(eoconfig.accounts_url % {'division': exact_division}, token, query=options, progress=lambda x: progress('Reading accounts '+x))
    return users


def get_current_division(token):
    url = eoconfig.base + '/v1/current/Me?$select=CurrentDivision'
    response = request(url, token)
    return response[0]['CurrentDivision']


def getDivisions(token):
    """
    Get the "current" division and return a dictionary of divisions
    so the user can select the right one.

    WARNING: Exact does NOT return all possible divisions, due to bugs.
    """
    if testmode():
        return 15972, {15972: 'Life Connexion', 1621446: 'C3 Church'}
    # The detection of divisions does not work when current is 1621446
    current = get_current_division(token)
    url = base + '/v1/%(division)i/hrm/Divisions?$select=Code,Description'
    url = url % {'division': current}
    divisions = request(url, token)
    divisions = {d['Code']: d['Description'] for d in divisions}
    return current, divisions


def getBtwCodes(division, token):
    options = {}
    users = request(eoconfig.accounts_url % {'division': division}, token, query=options)
    return users


def checkAuthorization(divisions, token):
    """ Check to which divisions the supplied token gives access.

        To check authorization, try to get the BTW codes for the division.
    """
    authorized = []
    for division in divisions:
        try:
            result = getBtwCodes(division, token)
            authorized.append(division)
        except:
            traceback.print_exc('GetBtwCodes Error')
            print('Not authorized', division)
            pass
    return authorized

def getAccessToken(code):
    params = {'code': code,
              'client_id': binquote(eoconfig.client_id),
              'grant_type': 'authorization_code',
              'client_secret': binquote(eoconfig.client_secret),
              'redirect_uri': binquote(eoconfig.redirect_uri)}
    response = request(eoconfig.token_url, method='POST', params=params)
    return response


def authenticateExact(func):
    if testmode():
        def request(*args, **kwargs):
            if 'token' not in kwargs:
                kwargs['token'] = 'dummy'
            return func(*args, **kwargs)
    else:
        def request(*args, **kwargs):
            print('Authenticating request', cherrypy.request.method, kwargs)
            # Check if the token parameter is set
            if 'token' in kwargs:
                return func(*args, **kwargs)
            # Check if the OAUTH code was provided
            if 'code' in kwargs:
                print('URL:', cherrypy.url())
                token = getAccessToken(kwargs['code'])
                kwargs['token'] = token['access_token']
                return func(*args, **kwargs)
            # Otherwise let the user login and get the OAUTH token.
            values = '&'.join(['%s=%s'%(k, binquote(v)) \
                           for k, v in dict(client_id=eoconfig.client_id,
                                            redirect_uri=eoconfig.redirect_uri,
                                            response_type='code',
                                            force_login='0').items()])
            url = eoconfig.auth_url + '?' + values
            raise cherrypy.HTTPRedirect(url)
    return request


def test():
    # Setup a test server
    class TestServer:
        @cherrypy.expose
        @authenticateExact
        def index(self, **kwargs):
            pass

    cherrypy.config.update({'server.socket_port': 13958,
                            'server.socket_host': '0.0.0.0',
                            'server.ssl_certificate': 'server.crt',
                            'server.ssl_private_key': 'server.key',
                            'tools.sessions.on': True
                            })
    # cherrypy.quickstart(Overzichten(), '/', 'server.conf')
    th = threading.Thread(target=cherrypy.quickstart, args=[TestServer(), '/', 'server.conf'])
    th.start()

    # Walk through the Exact login sequence
    while True:
        time.sleep(1)
    request("https://start.exactonline.nl/api/oauth2/auth",
            query=dict(client_id='45e63a87-5943-4163-ab90-ccb23a738ad4',
                       redirect_uri='https://vandewaal.xs4all.nl:13958',
                       response_type='code',
                       force_login=1))
    pass


if __name__ == '__main__':
    test()
