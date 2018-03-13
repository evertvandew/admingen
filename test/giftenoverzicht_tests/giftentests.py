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


test_template = '''.. header::


        .. image:: %(logo)s
          :height: 1cm
          :align: left

.. footer::

  Life Connexion is een ANBI erkende organisatie
  
  Geregistreerd bij de Kamer van Koophandel onder nr. 50207040
  
  http://www.lifeconnexion.nl'''


testmail = '''### Beste gever,

In de bijlage ontvang je een overzicht van de bij ons geregistreerde giften over 2017. Als het goed is heb je ook periodiek overzichten ontvangen en kunnen bijhouden of je giften goed geregistreerd zijn. Mochten er toch nog dingen niet goed geregistreerd zijn, dan horen wij dat graag zo snel mogelijk.

### Fiscale aftrekbaarheid

Je ontvangt nu een overzicht dat je kunt gebruiken bij je jaaraangifte inkomstenbelasting. Je giften zijn tot 10 procent van je bruto belastbaar inkomen aftrekbaar. Indien je meer fiscale ruimte wenst om te geven kun je contact met ons opnemen over hoe je periodieke schenkingen kunt doen en daarmee meer fiscaal voordeel kunt behalen.

### Financiële gezondheid

Bovenal is het voor ons belangrijk dat je volledig vrijwillig en in lijn met je plannen en voornemen geeft. Ons doel is om zowel voor jou als voor Life Connexion financiële gezondheid te bereiken, nu, in de toekomst en zelfs voor de volgende generatie!

### Meer inzicht

Op de website van Life Connexion kun je meer informatie vinden over de inkomsten en uitgaven van Life Connexion. 

Met vriendelijke groet, 

Het administratieteam van Life Connexion

PS I Met dit email adres kan niet gecorrespondeerd worden. Vragen kun je stellen aan mailto:marloes@lifeconnexion.nl

PS II Het kan zijn dat je gift bij je bank afgeschreven is aan het einde van 2017, maar pas bij ons is ontvangen in 2018. In dat geval kun je kiezen of je de gift aanmerkt in 2017 of 2018. Wij kunnen geen overzicht verstrekken met die giften in 2017, maar je kunt je eigen afschrift gebruiken om het naar de Belastingdienst te onderbouwen.'''


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

        config.load_context()

        if os.path.exists('overzichtgen.db'):
            os.remove('overzichtgen.db')

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
            details = {'name': 'LifeConnexion',
                       'smtphost': 'mail.testing.nl',
                       'user': 'testgebruiker',
                       'password': 'ditiszeergeheim'
                       }
            for n, v in details.items():
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
                elem.send_keys(v)
            browser.find_element_by_tag_name("button").click()

            # Now use that organisation for testing the data processing
            browser.get('http://localhost:13958')
            browser.find_element_by_tag_name("button").click()

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