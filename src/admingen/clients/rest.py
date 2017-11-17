import urllib
import inspect
import asyncio
from requests import request

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

    def getAccessToken(self, code):
        params = {'code': code,
                  'client_id': binquote(self.client_id),
                  'grant_type': 'authorization_code',
                  'client_secret': binquote(self.client_secret),
                  'redirect_uri': binquote(self.redirect_uri)}
        response = request(self.token_url, method='POST', params=params)
        return response
