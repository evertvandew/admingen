from unittest import TestCase, main
import os.path
import os
from giftenoverzicht import run
from admingen.clients.exact_rest import ExactClientConfig
from admingen import config
from simulators.exact import RestSimulator
from threading import Thread
from requests import get
from socket import socket
import time



class TestServer(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oauthsim = RestSimulator(12345)
        root = os.path.abspath(os.path.dirname(__file__)+ '../../..')
        os.environ['ROOTDIR'] = root
        os.environ['PROJDIR'] = root + '/projects/giftenoverzicht'
        os.environ['SRCDIR'] = root + '/src'

    @classmethod
    def tearDownClass(cls):
        cls.oauthsim.terminate()

    def setUp(self):
        config.set_configdir(os.path.dirname(__file__) + '/config')
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

    def testConfig(self):
        conf = config.getConfig('exactclient')
        self.assertEqual(conf.base, 'http://localhost:12345')
        self.assertEqual(conf.auth_url, 'http://localhost:12345/oauth2/auth')
        self.assertEqual(type(conf).__name__, 'ExactClientConfig')


if __name__ == '__main__':
    main()