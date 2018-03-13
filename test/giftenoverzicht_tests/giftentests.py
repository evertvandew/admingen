from unittest import TestCase, main
import os.path
import os
from threading import Thread
from requests import get
from socket import socket
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from admingen.clients.exact_rest import ExactClientConfig
from admingen import config
from admingen.util import quitter
from simulators.exact import RestSimulator

confdir = os.path.dirname(__file__)+'/config'

from admingen import config
config.set_configdir(confdir)

import giftenoverzicht

downloaddir = '/tmp'

class TestServer(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oauthsim = RestSimulator(12345)
        root = os.path.abspath(os.path.dirname(__file__)+ '../../..')
        os.environ['ROOTDIR'] = root
        os.environ['PROJDIR'] = root + '/projects/giftenoverzicht'
        os.environ['SRCDIR'] = root + '/src'
        confdir = os.path.dirname(__file__) + '/config'
        config.set_configdir(confdir)

    @classmethod
    def tearDownClass(cls):
        cls.oauthsim.terminate()

    def setUp(self):
        config.set_configdir(os.path.dirname(__file__) + '/tmp')
        mydir = os.path.dirname(__file__)
        self.runner = Thread(target=giftenoverzicht.run)
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


    def testWithBrowser(self):
        chromeOptions = webdriver.ChromeOptions()
        prefs = {"download.default_directory": downloaddir}
        chromeOptions.add_experimental_option("prefs", prefs)
        browser = webdriver.Chrome(chrome_options=chromeOptions)

        # browser = webdriver.Chrome()
        with quitter(browser):
            browser.get('http://localhost:13958')
            while True:
                time.sleep(1)


    def testNoBrowser(self):
        r = get('http://localhost:13958/')
        while True:
            time.sleep(1)
        self.assertEqual(r.status_code, 200)
        pass

    def testConfig(self):
        conf = config.getConfig('exactclient')
        self.assertEqual(conf.base, 'http://localhost:12345')
        self.assertEqual(conf.auth_url, 'http://localhost:12345/oauth2/auth')
        self.assertEqual(type(conf).__name__, 'ExactClientConfig')


if __name__ == '__main__':
    main()