from unittest import TestCase, main
import os.path
from giftenoverzicht import run
from admingen.clients.exact_rest import ExactClientConfig
from simulators.exact import RestSimulator
from threading import Thread
from requests import get
from socket import socket
import time



testconfig = dict(base = 'http://localhost:12345',
    client_secret = 'ditiseentest',
    webhook_secret = 'blablablabla',
    client_id = '1',
    redirect_uri = 'http://localhost:13958',
    TESTMODE = False)


class TestServer(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oauthsim = RestSimulator(12345)
    @classmethod
    def tearDownClass(cls):
        cls.oauthsim.terminate()

    def setUp(self):
        ExactClientConfig().update(testconfig)
        mydir = os.path.dirname(__file__)
        self.runner = Thread(target=run)
        self.runner.setDaemon(True)
        self.runner.start()

        # Wait until both servers are listening
        for p in [12345, 13958]:
            while True:
                try:
                    s = socket()
                    s.connect(('localhost', 12345))
                    s.close()
                    break
                except ConnectionRefusedError:
                    s.close()
                    time.sleep(0.01)


    def testNoBrowser(self):
        r = get('http://localhost:13958/')
        self.assertEqual(r.status_code, 200)
        pass


if __name__ == '__main__':
    main()