
import os, os.path
import threading
import sys
import asyncio
from . import config
from .db_api import openDb, sessionScope, DbTable, select, delete, Required, Set, commit, orm
from .keyring import KeyRing
from .email import sendmail
from .clients.rest import OAuth2
from .servers import mkUnixServer, Message, expose, serialize, deserialize, update
from . import logging


@DbTable
class Task:
    name: str
    schedule: str
    details: Set('TaskDetails')


@DbTable
class TaskDetails:
    task : Task
    component: str
    settings: str


@config.configtype
class worker_config:
    adminmail='evert.vandewaal@xs4all.nl'
    appname='Generic Worker'
    keyring='$OPSDIR/workerring.enc'
    readersock='$OPSDIR/worker.sock'
    database='sqlite://$OPSDIR/worker.db'



appconfig = worker_config()

bootmail = '''I have restarted, and need my keyring unlocked!

Your faithful servant, {appconfig.appname}'''

if False:
    # First let the maintainer know we are WAITING!
    sendmail(appconfig.adminmail, appconfig.selfmail,
             'Waiting for action',
             bootmail % appconfig.appname)

def Worker(workercls):
    class WorkerCls:
        keyring = None
        exact_token = None
        oauth = None
        config = appconfig

        @staticmethod
        def sockname():
            p = appconfig.readersock
            if not os.path.isabs(p):
                return os.path.join(config.opsdir, p)
            return p

        @staticmethod
        def keyringname():
            p = appconfig.keyring
            if os.path.isabs(p):
                return p
            return os.path.join(config.opsdir, p)

        @staticmethod
        def secret_key(task_id, secret_cls):
            return 'task{}_{}'.format(task_id, secret_cls.__name__)

        def __init__(self, cls=workercls):
            self.cls = cls
            self.keyring = None
            self.tasks = {}
            self.errors = {}
            self.runs = {}

        @expose
        def unlock(self, password):
            """ Supply the keychain password to the application.
                This allows the tasks to be instantiated.
            """
            self.keyring = KeyRing(self.keyringname(), password)
            self.reload()

        @expose
        def reload(self):
            with sessionScope():
                task_names = {t.id: t.name for t in list(Task.select())}
                task_config = {}
                for d in select(t for t in TaskDetails):
                    task_config.setdefault(d.task.id, {})[d.component] = d.settings

                for task_id, details in task_config.items():
                    config = [deserialize(t, details[t.__name__])
                              for t in self.cls.__annotations__['config']]
                    keys = [(t, self.secret_key(task_id, t))
                            for t in self.cls.__annotations__['secrets']]
                    optional_config = []
                    optional_keys = []
                    if 'optional_config' in self.cls.__annotations__:
                        optional_config = [deserialize(t, details[t.__name__])
                                  for t in self.cls.__annotations__['optional_config'] if t.__name__ in details]
                        optional_keys = [(t, self.secret_key(task_id, t))
                                   for t in self.cls.__annotations__['optional_secrets']]
                    missing = [k for k in keys if k[1] not in self.keyring]
                    if missing:
                        msg = 'The keyring is missing the following details: %s'%[t[1] for t in missing]
                        logging.error(msg)
                        raise RuntimeError(msg)

                    secrets = [t(**self.keyring[k]) for t, k in keys]
                    secrets += [t(**self.keyring[k]) for t, k in optional_keys if k in self.keyring]

                    # Test if all settings are set...
                    if not all([*(config), *secrets]):
                        self.errors[task_names[task_id]] = 'Some configuration is missing'
                        logging.error('Task %s missing some configuration'%task_names[task_id])
                    else:
                        self.tasks[task_names[task_id]] = self.cls(task_id, config+optional_config, secrets)

        @expose
        def status(self):
            return dict(keyring='unlocked' if self.keyring else 'locked',
                        tasks=[t for t in self.tasks],
                        errors=self.errors,
                        exact_online='authenticated' if self.exact_token else 'locked')

        @expose
        def setauthorizationcode(self, code):
            """ The authorization is used to get the access token """
            if self.exact_token:
                raise RuntimeError('The system is already authorized')
            token = self.oauth.getAccessToken(code)
            self.exact_token = token

            # Set a timer to refresh the token
            loop = asyncio.get_event_loop()
            loop.call_later(int(token['expires_in']) - 550, self.refreshtoken)

        def refreshtoken(self):
            """ Refresh the current access token """
            token = self.oauth.getAccessToken()
            self.exact_token = token

            # Set a timer to refresh the token again
            loop = asyncio.get_event_loop()
            loop.call_later(int(token['expires_in']) - 550, self.refreshtoken)

        @expose
        def runOnce(self):
            for name, t in self.tasks.items():
                try:
                    logging.debug('Starting task %s' % name)
                    t.run()
                except:
                    logging.exception('Exception when running task '+ name)
                    break


        async def scheduler(self):
            while True:
                # Wait one second
                await asyncio.sleep(1)
                print ('tick')

                self.runOnce()


        @expose
        def exit(self):
            logging.warning('Terminating worker process')
            sys.exit(0)

        @staticmethod
        @logging.log_exceptions
        def run(cls=workercls):
            # The database is created by the client!
            openDb(appconfig.database, create=False)

            print('Starting worker')

            # In test mode, we need to create our own event loop
            if threading.current_thread() != threading.main_thread():
                # Only the main thread has an event loop. If necessary, start a new one.
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            worker = Worker(cls)()
            # Start serving requests & doing work
            server = mkUnixServer(worker, worker.sockname())
            loop = asyncio.get_event_loop()
            loop.create_task(server)
            #loop.create_task(worker.scheduler())
            loop.run_forever()

    return WorkerCls
