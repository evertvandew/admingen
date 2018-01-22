""" Run a server that writes paypal transactions to exact.

There are two processes running: the frontend, where the user can view system status and
edit settings. The backend actually performs the work. The frontend will query the backend
through a very small API. The frontend does NOT access the database or other stored data,
for security purposes.

"""

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

from paypal_exact.worker import Worker, PaypalExactTask


def WorkerConfigEditor(details, secrets):
    details_columns = [generateFields(d)[:] for d in details]
    details_secrets = [generateFields(d)[:] for d in secrets]

    class Crud:
        @cherrypy.expose
        def index(self):
            """ Give an overview of the tasks that are available, and link to editing and deleting """
            pass

        @cherrypy.expose
        def edit(self, id, **kwargs):
            """ View the details of a single task, and allow editing """
            settings = [TaskHandler.worker.getSettings(id, d.__name__) for d in details]

            def success(**kwargs):

                raise cherrypy.HTTPRedirect('view?id=%s' % kwargs['id'])

            forms = [Div(SimpleForm(*cols, defaults=s, success=success, cancel='index')
                                    for cols, s in zip(details_columns, settings),
                         # Add a button to set the secrets
                         Button()
                         )]

            return Page(Title('Configuratie van een taak'),
                        SimpleForm())

        @cherrypy.expose
        def delete(self, id):
            """ Delete a specific task """
            pass



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

    worker_details = WorkerConfigEditor(PaypalExactTask.config, PaypalExactTask.secrets)

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
        raise cherrypy.HTTPRedirect('/')


@contextmanager
def production_worker():
    """ Runs the worker in a separate process """
    # Run the worker and create a proxy to it
    home = os.path.dirname(__file__)

    p = subprocess.Popen(['/usr/bin/env', 'python3.6', 'worker.py'], cwd=home)
    worker = unixproxy(Worker, Worker.sockname)
    TaskHandler.worker = worker

    # let the worker run
    try:
        yield
    finally:
        # Now stop the worker
        worker.exit()
        # Wait at most 1 second, then terminate the process
        try:
            p.wait(1)
        except subprocess.TimeoutExpired:
            # Terminat the process
            p.terminate()
        p.wait()


@contextmanager
def test_worker():
    # Just make the worker proxy the actual worker
    worker = Worker()
    TaskHandler.worker = worker
    yield
    # Nothing to do when cleaning up

@contextmanager
def threaded_worker():
    """ Runs the worker in a separate thread, to test the server mechanisms """
    th = threading.Thread(target=Worker.run)
    th.setDaemon(True)
    th.start()
    worker = unixproxy(Worker, Worker.sockname)
    TaskHandler.worker = worker

    # let the worker run
    try:
        yield

    finally:
        # Now stop the worker
        worker.exit()
        th.join()


def run():
    worker = threaded_worker if config.testmode() else production_worker
    with worker():
        cherrypy.config.update({'server.socket_port': 13959})
        cherrypy.quickstart(TaskHandler(), '/')

if __name__ == '__main__':
    run()
