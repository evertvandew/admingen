import urllib
import inspect
import asyncio
import requests
import json
import time
import threading

import cherrypy
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException


def restapi(cls):
    """ Decorator that turns a class taxonomy into a REST api """
    return cls



def binquote(value):
    """
    We use quote() instead of urlencode() because the Exact Online API
    does not like it when we encode slashes -- in the redirect_uri -- as
    well (which the latter does).
    """
    return urllib.parse.quote(value.encode('utf-8'))



class OAuthError(RuntimeError):
    pass


class OAuth2:
    def __init__(self, token_url, client_id, client_secret, redirect_uri):
        # Copy all elements blindly into the internal dict
        self.token_url, self.client_id, self.client_secret, self.redirect_uri = \
            token_url, client_id, client_secret, redirect_uri
        self.token = None

    def getAccessToken(self, code=None):
        """ Get a new access token from an authorization code, or refresh the current token """
        params = {'client_id': binquote(self.client_id),
                  'client_secret': binquote(self.client_secret),
                  'redirect_uri': binquote(self.redirect_uri)}
        if code:
            params['code'] = code
            params['grant_type'] = 'authorization_code'
        else:
            assert self.token, 'Need a valid token before refreshing'
            params['refresh_token'] = self.token['refresh_token']
            params['grant_type'] = 'refresh_token'

        data = '&'.join(['%s=%s'%it for it in params.items()])
        response = requests.post(self.token_url, data=data.encode('utf8'),
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
        assert response.status_code == 200, 'get Access Token failed'
        self.token = response.json()
        self.token['birth'] = time.time()
        return self.token

    def headers(self):
        return {'Authorization': 'Bearer ' + self.token['access_token']}




def loginOAuth(username, password, client_id, client_secret, redirect_uri):
    """ Get the initial token necessary for oauth2 authentication """
    # First experiments with the exact online login
    PORT = 13957
    base = 'https://start.exactonline.nl/api'
    auth_url = base + '/oauth2/auth'
    token_url = base + '/oauth2/token'
    the_code = ''

    # Start a (temporary) web server for handling the authentication code redirect
    class RedirectServer:
        @cherrypy.expose
        def index(self, code):
            nonlocal the_code
            the_code = code
        @cherrypy.expose
        def shutdown(self):
            cherrypy.engine.exit()

    conf = {'global': {'server.socket_port': PORT, 'server.socket_host': '0.0.0.0'}}
    th = threading.Thread(target=cherrypy.quickstart, args=[RedirectServer(), '/', conf])
    th.start()

    # Get a webclient for going through the login process
    browser = webdriver.Chrome()
    params = dict(client_id=client_id,
                  redirect_uri=redirect_uri,
                  response_type='code',
                  force_login='1')
    url = auth_url + '?' + '&'.join('='.join(i) for i in params.items())
    browser.get(url)

    # Fill in the user credentials
    elem = browser.find_element_by_name("UserNameField")
    elem.send_keys(username)
    elem = browser.find_element_by_name("PasswordField")
    elem.send_keys(password)

    # Submit the details
    elem = browser.find_element_by_name("LoginButton")
    elem.click()

    # Wait until the oauth code is submitted
    while not the_code:
        time.sleep(0.1)

    # We can close the browser and http server
    browser.quit()
    requests.get('http://localhost:%i/shutdown'%PORT)
    th.join()

    # Now use the code to get a token and return it
    params = {'code': the_code,
              'client_id': binquote(client_id),
              'grant_type': 'authorization_code',
              'client_secret': binquote(client_secret),
              'redirect_uri': binquote(redirect_uri)}
    data = '&'.join(['%s=%s' % it for it in params.items()])
    response = requests.post(token_url, data=data.encode('utf8'),
                             headers={'Content-Type': 'application/x-www-form-urlencoded'})
    if response.status_code != 200:
        raise OAuthError('Get Access Token failed')
    token = response.json()
    token['birth'] = time.time()
    return token


def refreshToken(token, client_id, client_secret, redirect_uri):
    """ Simply refresh an existing token. """
    base = 'https://start.exactonline.nl/api'
    auth_url = base + '/oauth2/auth'
    token_url = base + '/oauth2/token'

    params = {'client_id': binquote(client_id),
              'client_secret': binquote(client_secret),
              'redirect_uri': binquote(redirect_uri),
              'refresh_token': token['refresh_token'],
              'grant_type': 'refresh_token'}

    data = '&'.join(['%s=%s' % it for it in params.items()])
    response = requests.post(token_url, data=data.encode('utf8'),
                             headers={'Content-Type': 'application/x-www-form-urlencoded'})
    if response.status_code != 200:
        raise OAuthError('Refresh Access Token failed')
    token = response.json()
    token['birth'] = time.time()
    return token
