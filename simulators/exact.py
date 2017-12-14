
import cherrypy
import multiprocessing
import time
import secrets
import json

class Oauth:
    @cherrypy.expose
    def auth(self, client_id, redirect_uri, response_type, force_login):
        self.code = secrets.token_urlsafe(16)
        self.client_id = client_id
        url = redirect_uri + '?code=%s'%self.code
        raise cherrypy.HTTPRedirect(url)
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def token(self, client_id, code, client_secret, grant_type, redirect_uri):
        return dict(access_token=secrets.token_urlsafe(16),
                   token_type='token',
                   expires_in=3600,
                   refresh_token=secrets.token_urlsafe(16))

class RestApi:
    pass


class RestSimulator(multiprocessing.Process):
    oauth2 = Oauth()
    v1 = RestApi()

    def __init__(self, port):
        self.port = port
        multiprocessing.Process.__init__(self)
        self.start()

    def run(self):
        cherrypy.quickstart(self, '/', {'global' :{'server.socket_port': self.port}} )


if __name__ == '__main__':
    r = RestSimulator(12345)
    while True:
        time.sleep(1)
