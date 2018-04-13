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
from urllib.parse import urlparse

from admingen import keyring
from admingen.logging import log_exceptions
from admingen.servers import unixproxy, ServerError
from admingen import config
from admingen.htmltools import *
from admingen.keyring import DecodeError
from admingen.db_api import fields, the_db, openDb

from paypal_exact.worker import PaypalExactTask, paypal_export_config
from admingen.worker import Worker, Task, TaskDetails, appconfig


def taskdetails_editor(base):
    """ Wrap a basic CRUD editor with additional editors for the task details """
    classes = {d.__name__: d for d in PaypalExactTask.__annotations__['config']}

    def mkgetter(clsname):
        def getter():
            """ Get the current values for all elements in a structure """
            i = cherrypy.request.params.get('id')
            if not i:
                raise cherrypy.HTTPError(400, 'No ID supplied')
            with sessionScope():
                rec = TaskDetails.select(lambda x: x.task.id==i and x.component==clsname).first()
                data = {'id': i}
                if rec:
                    ud = {clsname+k:v for k, v in json.loads(rec.settings).items()}
                    data.update(ud)
                return data
        return getter

    detail_editors = [annotationsForm(d, extra_fields=[Hidden('id')],
                                      success=lambda **kwargs:None,
                                      getter=mkgetter(d.__name__),
                                      prefix=d.__name__)
                      for d in PaypalExactTask.__annotations__['config']]
    headers = ['Details aanpassen: '+c.__name__ for c in PaypalExactTask.__annotations__['config']]

    class wrapper:
        @cherrypy.expose
        def index(self, **kwargs):
            return Page(base.index(**kwargs))
        @cherrypy.expose
        def view(self, id, **kwargs):
            return Page(base.view(id, **kwargs))
        @cherrypy.expose
        def delete(self, **kwargs):
            if cherrypy.request.method == 'POST':
                # The user indeed wants to delete this item.
                # Delete all associated records first.
                if 'id' not in kwargs:
                    raise cherrypy.HTTPError(400, 'Missing argument "id"')
                with sessionScope():
                    TaskDetails.delete(lambda x: x.task_id == kwargs['id'])
            return Page(base.delete(**kwargs))
        @cherrypy.expose
        def edit(self, **kwargs):
            if cherrypy.request.method == 'POST':
                # Extract the elements for the component configurations.
                taskid = cherrypy.request.params['id']
                with sessionScope():
                    for index, clsname in enumerate(classes):
                        data = {k.replace(clsname, ''):v for k,v in kwargs.items() if k.startswith(clsname)}
                        if not data:
                            continue
                        datajson = json.dumps(data)
                        # either create or update the database record
                        rec = TaskDetails.select(lambda x: x.task.id==taskid and x.component==clsname).first()
                        if rec is None:
                            rec = TaskDetails(component=clsname, task=Task[taskid], settings=datajson)
                        else:
                            rec.settings = datajson
            return Page(Collapsibles(detail_editors, headers),
                        base.edit(**kwargs),
                        )
    return wrapper()


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
        #elif status['exact_online'] == 'locked':
        #    elements = [Div('Exact online moet ontsloten worden'),
        #                Button('Ontsluit Exact Online', self.login.__name__)]
        return Page(Title('Status Overzicht'), *elements)

    def dummypage(self, *args):
        return joinElements(*args)

    worker_details = taskdetails_editor(generateCrud(Task, Page=dummypage))

    @cherrypy.expose
    def unlock(self, password=None):
        def verify(password):
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
    # We need to start the database directly
    logging.debug('Opening application database %s'%appconfig.database)
    openDb(appconfig.database, create=True)

    # Run the worker and create a proxy to it
    home = config.projdir

    logging.debug('starting worker in %s'%home)
    p = subprocess.Popen(['/usr/bin/env', 'python3.6', 'worker.py'], cwd=home)
    WorkerCls = Worker(PaypalExactTask)
    worker = unixproxy(WorkerCls, WorkerCls.sockname())
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
    # We need to start the database directly
    openDb('sqlite://:memory:', create=True)

    # Just make the worker proxy the actual worker
    worker = Worker()
    TaskHandler.worker = worker
    yield
    # Nothing to do when cleaning up

@contextmanager
def threaded_worker():
    """ Runs the worker in a separate thread, to test the server mechanisms """
    # We need to start the database directly
    openDb('sqlite://:memory:', create=True)

    th = threading.Thread(target=Worker.run)
    th.setDaemon(True)
    th.start()
    worker = unixproxy(Worker, Worker.sockname())
    TaskHandler.worker = worker

    # let the worker run
    try:
        yield

    finally:
        # Now stop the worker
        worker.exit()
        th.join()


def run():
    worker = test_worker if config.testmode() else production_worker
    with worker():
        cherrypy.config.update({'server.socket_port': 13959})
        cherrypy.quickstart(TaskHandler(), '/', {  "/": {
            "tools.staticdir.debug": True,
            "tools.staticdir.root": os.path.dirname(__file__),
            "tools.trailing_slash.on": True,
            "tools.staticdir.on": True,
            "tools.staticdir.dir": "./public"
          }
        })

if __name__ == '__main__':
    run()
