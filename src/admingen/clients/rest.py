import urllib
import inspect
import asyncio
import requests
import json
import time

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
