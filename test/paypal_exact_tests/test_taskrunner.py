""" Test the paypal-exact converter in full operational mode. """

import os
import os.path
import glob
from unittest import TestCase
import subprocess
import json
import threading
import time

from admingen import config
from admingen.db_api import sessionScope, openDb
from admingen.servers import unixproxy
from admingen.dataclasses import dataclass, asdict
from admingen.keyring import KeyRing
from admingen.worker import Worker, appconfig

from projects.paypal_exact import Task, TaskDetails


testdir = os.path.dirname(__file__)
rootdir = os.path.abspath(testdir + '/../..')

test_password = 'this is a secret'


@dataclass
class TestConfig:
    a: int
    b: str


@dataclass
class TestSecrets:
    c: int
    d: str

class TestTask:
    config: [TestConfig]
    secrets: [TestSecrets]

    runned = []

    def __init__(self, client_id, config, secrets):
        assert len(config) == 1
        assert len(secrets) == 1
        assert isinstance(config[0], TestConfig)
        assert isinstance(secrets[0], TestSecrets)
        self.config = config
        self.secrets = secrets

    def run(self):
        print ('Run', time.time())
        TestTask.runned.append(time.time())


class tests(TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure there are no artifacts from previous tests
        for fname in glob.glob(testdir+'/tmp/*') + glob.glob(testdir+'/*.db'):
            os.remove(fname)

        # Ensure the relevant environment variables are set
        os.environ['PROJECTNAME'] = 'paypal_exact'
        for e in ['LOGDIR', 'RUNDIR', 'OPSDIR']:
            os.environ[e] = testdir+'/tmp'
        os.environ['CONFDIR'] = testdir

        config.load_context()

        cls.p = None # subprocess.Popen(['python3.6', 'run', 'paypal_exact'], cwd=rootdir)

    @classmethod
    def tearDownClass(cls):
        if cls.p:
            cls.p.terminate()

    def testWorker(self):
        # Connect with the taskrunner
        if self.p:
            client: Worker = unixproxy(Worker, appconfig.sockname())
        else:
            openDb(appconfig.database, create=True)
            client: Worker = Worker(TestTask)()

        # check the status
        status = client.status()
        print (status)

        self.assertEqual(status['keyring'], 'locked')
        self.assertEqual(status['tasks'], [])
        self.assertEqual(status['exact_online'], 'locked')

        # Create a new task using the database

        # Create a configuration
        wc = TestConfig(a=21, b='Dit is een test')
        with sessionScope():
            _ = Task(name='testtask', schedule='*')
            _.details = TaskDetails(component=TestConfig.__name__,
                                    settings=json.dumps(asdict(wc)))

        with sessionScope():
            t = Task.select().first()
            self.assertTrue(t)
            d = t.details
            self.assertEqual(len(d), 1)


        # Fill the keyring
        kr = KeyRing(client.keyringname(), test_password)
        kr[client.secret_key(1, TestSecrets)] = TestSecrets(12345, test_password)

        # Unlock the worker: a task should be started.
        client.unlock(test_password)

        status = client.status()
        self.assertEqual(status['keyring'], 'unlocked')
        self.assertEqual(len(status['tasks']), 1)
        self.assertEqual(len(status['errors']), 0)

        # Check if the task is run properly
        for _ in range(10):
            client.runOnce()

        self.assertEqual(len(TestTask.runned), 10)
        pass