""" Run a server that writes paypal transactions to exact """

import secrets
from collections import namedtuple
import requests
import cherrypy
import time
import os
import os.path
import subprocess
import threading
from contextlib import contextmanager

from admingen import keyring
from admingen.logging import log_exceptions
from admingen.servers import unixproxy, ServerError
from admingen import config
from admingen.htmltools import *
from admingen.keyring import DecodeError

from paypal_exact.worker import Worker


class TaskHandler:
    worker = None
    @cherrypy.expose
    def index(self):
        # Request the current status
        status = self.worker.status()
        elements = []
        if status['keyring'] == 'locked':
            elements = [Div('De sleutelring is nog gesloten: de applicatie kan niet draaien'),
                        Button('Open de sleutelring', self.unlock.__name__)]
        elif status['exact_online'] == 'locked':
            elements = [Div('Exact online moet ontsloten worden'),
                        Button('Ontsluit Exact Online', self.login.__name__)]
        return Page(Title('Status Overzicht'), *elements)

    @cherrypy.expose
    def unlock(self, password=None):
        def verify():
            try:
                self.worker.unlock(password)
                return {}, {}
            except ServerError:
                return {}, {'password': 'Wrong Password'}
        def success():
            raise cherrypy.HTTPRedirect('/')
        return Page(Title('Open de sleutelring'), SimpleForm(EnterPassword('password'),
                                                             validator=verify,
                                                             success=success))


    @cherrypy.expose
    def login(self):
        args = dict(client_id='49b30776-9a29-4a53-b69d-a578712e997a',
                    redirect_uri='http://paypal_reader.overzichten.nl:13959/oauth_code',
                    response_type='code',
                    force_login='0')
        args = '&'.join('%s=%s'%i for i in args.items())
        raise cherrypy.HTTPRedirect("https://start.exactonline.nl/api/oauth2/auth?"+args)

    @cherrypy.expose
    def oauth_code(self, code=None, **kwargs):
        if code:
            self.worker.setauthorizationcode(code)


@contextmanager
def autoexit(p):
    # let the worker run
    yield
    # Now stop the worker
    worker.exit()
    # Wait at most 1 second, then terminate the process
    try:
        p.wait(1)
    except subprocess.TimeoutExpired:
        # Terminat the process
        p.terminate()
    p.wait()


def run():
    # Run the worker and create a proxy to it
    home = os.path.dirname(__file__)

    if not config.testmode():
        p = subprocess.Popen(['/usr/bin/env', 'python3.6', 'worker.py'], cwd=home)
    else:
        p = threading.Thread(target=Worker.run)
        p.setDaemon(True)
        p.start()

    with autoexit(p):
        worker = unixproxy(Worker, Worker.sockname)
        TaskHandler.worker = worker
        cherrypy.config.update({'server.socket_port': 13959})
        cherrypy.quickstart(TaskHandler(), '/')

if __name__ == '__main__':
    run()
