from unittest import TestCase, main
import os.path
import os
import threading
from requests import get
from socket import socket
import time

import cherrypy
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from admingen.clients.exact_rest import ExactClientConfig
from admingen import config
from admingen.util import quitter
from admingen.clients.smtp import mkclient
from simulators.exact import RestSimulator
from simulators import smtp

confdir = os.path.dirname(__file__)+'/config'

from admingen import config
config.set_configdir(confdir)

import giftenoverzicht

downloaddir = '/tmp'


test_template = '''.. header::


        .. image:: %(logo)s
          :height: 1cm
          :align: left

.. footer::

  Life Connexion is een ANBI erkende organisatie
  
  Geregistreerd bij de Kamer van Koophandel onder nr. 50207040
  
  http://www.lifeconnexion.nl'''


testmail = '''### Beste gever,

'''



smtpdetails = {'name': 'LifeConnexion',
               'smtphost': 'localhost:8025',
               'user': '',
               'password': ''
              }


# There is a bug in cherrypy that causes it to hang during the tests.
# Monkey-patch it!
from cherrypy.process.wspbus import Bus
def myBlock(self, interval=0.1):
    # Don't wait nor exit the process...
    return
Bus.block = myBlock

class TestServer(TestCase):
    @classmethod
    def setUpClass(cls):
        # Start the simulator for Exact
        cls.oauthsim = RestSimulator(12345)
        root = os.path.abspath(os.path.dirname(__file__)+ '../../..')
        os.environ['ROOTDIR'] = root
        os.environ['PROJDIR'] = root + '/projects/giftenoverzicht'
        os.environ['SRCDIR'] = root + '/src'
        confdir = os.path.dirname(__file__) + '/config'
        config.set_configdir(confdir)

        config.load_context()

        if os.path.exists('overzichtgen.db'):
            os.remove('overzichtgen.db')

        # Start the giftenoverzicht server
        config.set_configdir(os.path.dirname(__file__) + '/tmp')
        mydir = os.path.dirname(__file__)
        cls.runner = threading.Thread(target=giftenoverzicht.run)
        cls.runner.setDaemon(True)
        cls.runner.start()

        # Start the SMTP simulator
        cls.smtpsim = smtp.loop()

        # Wait until all servers are listening
        for p in [12345, 13958, 8025]:
            while True:
                try:
                    s = socket()
                    s.connect(('localhost', p))
                    s.close()
                    break
                except (Exception):
                    s = None
                    time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.oauthsim.terminate()
        cls.smtpsim.stop()
        cherrypy.engine.exit()



    def testWithBrowser(self):
        chromeOptions = webdriver.ChromeOptions()
        prefs = {"download.default_directory": downloaddir}
        chromeOptions.add_experimental_option("prefs", prefs)
        browser = webdriver.Chrome(chrome_options=chromeOptions)
        browser.set_page_load_timeout(10)  # seconds

        # browser = webdriver.Chrome()
        with quitter(browser):
            # First create an organisation for testing
            browser.get('http://localhost:13958/smtp_details')
            elem = browser.find_element_by_name("username")
            elem.send_keys('test')
            elem = browser.find_element_by_name("password")
            elem.send_keys('testingtesting')
            elem = browser.find_element_by_tag_name("button")
            elem.click()
            elem = browser.find_element_by_tag_name("i")
            elem.click()
            for n, v in smtpdetails.items():
                elem = browser.find_element_by_name(n)
                elem.send_keys(v)
            browser.find_element_by_tag_name("button").click()

            browser.get('http://localhost:13958/organisaties/add')
            details = {'name': 'Lifeconnexion',
                       'description': 'Life Connexion, Amersfoort',
                       'mailfrom': 'giften@lifeconnexion.nl',
                       'gift_accounts': '8000 8050 8100 8150 8200 8800 8900 8990 8991',
                       'template': test_template,
                       'mail_body': testmail,
                       'admin_email': 'info@lifeconnexion.nl',
                       'exact_division': '15972',
                       'admin_id': '102'}
            for n, v in details.items():
                elem = browser.find_element_by_name(n)
                elem.clear()
                elem.send_keys(v)
            browser.find_element_by_tag_name("button").click()

            # Now use that organisation for testing the data processing
            while True:
                time.sleep(1)
            browser.get('http://localhost:13958')
            browser.find_element_by_tag_name("button").click()

            details = {'year': '2017',
                       'from': '1',
                       'until': '12'}
            for n, v in details.items():
                elem = browser.find_element_by_name(n)
                elem.clear()
                elem.send_keys(v)
            browser.find_element_by_tag_name("button").click()

            # Wait until the fourth button is highlighted, meaning processing is done
            while True:
                tables = browser.find_elements_by_tag_name("tr")
                if tables:
                    break

            # Try to download an overview
            table = tables[0]
            row = table.find_elements_by_tag_name('td')[1]
            # Download the PDF
            btns = row.find_elements_by_tag_name('a')
            btns[0].click()
            # Send the email
            gotmail = False
            def onMail(mailfrom, rcpttos, data):
                nonlocal gotmail
                gotmail = True
            smtp.callback = onMail

            btns[1].click()

            while not gotmail:
                time.sleep(0.1)

    def testNoBrowser(self):
        while True:
            try:
                r = get('http://localhost:13958/')
                break
            except:
                time.sleep(0.1)
        self.assertEqual(r.status_code, 200)
        pass

    def testConfig(self):
        conf = config.getConfig('exactclient')
        self.assertEqual(conf.base, 'http://localhost:12345')
        self.assertEqual(conf.auth_url, 'http://localhost:12345/oauth2/auth')
        self.assertEqual(type(conf).__name__, 'ExactClientConfig')

    def testEmail(self):
        gotmail = False
        def onEmail(mailfrom, tos, data):
            nonlocal gotmail
            gotmail = True
        smtp.callback = onEmail
        smtp_c = mkclient(smtpdetails['smtphost'])
        smtp_c.sendmail(__file__, 'test@localhost', b'Dit is een test')
        while not gotmail:
            time.sleep(0.1)


if __name__ == '__main__':
    main()