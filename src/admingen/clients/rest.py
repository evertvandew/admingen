import urllib
import inspect
import asyncio
import requests
import json
import time
import threading
import logging

import cherrypy
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException


from dataclasses import dataclass
from admingen.keyring import KeyRing

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


@dataclass
class OAuthDetails:
    token_url: str
    client_id: str
    client_secret: str


def loginOAuth(username, password, twophase_code, details: OAuthDetails):
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
    params = dict(client_id=details.client_id,
                  redirect_uri=details.token_url,
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

    # Fill in the authentication code (2-step)
    if twophase_code:
        elem = browser.find_element_by_name("ResponseTokenTotp$Key")
        elem.send_keys(twophase_code)

        # Submit the details
        elem = browser.find_element_by_name("LoginButton")
        elem.click()

    # Wait until the oauth code is submitted
    start = time.time()
    while not the_code:
        time.sleep(0.1)
        if time.time()-start > 20:
            raise RuntimeError('Did not receive token...')

    # We can close the browser and http server
    browser.quit()
    requests.get('http://localhost:%i/shutdown'%PORT)
    th.join()

    # Now use the code to get a token and return it
    params = {'code': the_code,
              'client_id': binquote(details.client_id),
              'grant_type': 'authorization_code',
              'client_secret': binquote(details.client_secret),
              'redirect_uri': binquote(details.token_url)}
    data = '&'.join(['%s=%s' % it for it in params.items()])
    response = requests.post(token_url, data=data.encode('utf8'),
                             headers={'Content-Type': 'application/x-www-form-urlencoded'})
    if response.status_code != 200:
        raise OAuthError('Get Access Token failed')
    token = response.json()
    token['birth'] = time.time()
    return token


def refreshToken(token, details: OAuthDetails):
    """ Simply refresh an existing token. """
    base = 'https://start.exactonline.nl/api'
    auth_url = base + '/oauth2/auth'
    token_url = base + '/oauth2/token'

    params = {'client_id': binquote(details.client_id),
              'client_secret': binquote(details.client_secret),
              'redirect_uri': binquote(details.token_url),
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


class TokenStoreApi:
    def get(self)->bytes:
        raise NotImplementedError
    def set(self, token:bytes):
        raise NotImplementedError


class FileTokenStore(TokenStoreApi):
    def __init__(self, path):
        self.path = path
        self.token = self.get()
    def get(self):
        try:
            with open(self.path, 'r') as f:
                return json.load(f)
        except:
            return None
    def set(self, token):
        with open(self.path, 'w') as f:
            json.dump(token, f)


def OAuth2(tokenstore: TokenStoreApi, details: OAuthDetails, getInput=input):
    def headers():
        token = tokenstore.token

        # If necessary, get the initial token
        if not token:
            logging.info('Getting an initial oauth token')
            print ('We have no starting token! Please supply the necessary details')
            username = getInput('Username')
            password = getInput('Password')
            authcode = getInput('Authentication Code')
            if not (username and password and authcode):
                raise RuntimeError("Could not retrieve oauth login details from %s"%getInput)
            token = loginOAuth(username, password, authcode, details)
            tokenstore.set(token)

        # Check if we need to refresh the token
        if time.time() - token['birth'] > int(token['expires_in']):
            logging.info('Refreshing oauth token')
            token = refreshToken(token, details)
            tokenstore.set(token)

        return {'Authorization': 'Bearer ' + token['access_token']}
    return headers


if __name__ == '__main__':
    # This code will load the initial OAuth2 Token, interacting with the user.
    pw = input('Please give password for oauth keyring')
    ring = KeyRing('oauthring.enc', pw)
    details = ring['oauthdetails']
    details = OAuthDetails(**details)
    oa = OAuth2(FileTokenStore('temptoken.json'), details, ring.__getitem__)
    print (oa())
