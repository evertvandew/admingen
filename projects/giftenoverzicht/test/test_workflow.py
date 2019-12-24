""" Test the giftenoverzicht workflow

This file tests the giftenoverzicht application from a user standpoint. It tests the following
actions:
  * Creating a new user
  * Creating a new organisation
  * Setting the SMTP details
  * Retrieving an administration
  * Generating financial reports
  * Sending a single mail
  * Sending a batch of mails
  * Again changing the organisation and smtp details
  * Generating and mailing a new batch

The tests use selenium for controlling a webbrowser.
"""

import unittest
import os, os.path
import time
import shutil
import subprocess
from dataclasses import asdict
from selenium import webdriver

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

from giftenoverzicht import run, Overzichten, SmtpDetails
from admingen.clients import smtp

server = None
exact_process = None
homedir = os.path.normpath(os.path.dirname(__file__) + '/../../..')
testdir = os.path.dirname(__file__)
downloaddir = testdir+'/downloads'

if False:
    def stop_server():
        global server
        server.terminate()

    def start_server():
        global server
        import subprocess
        if server:
            stop_server()
        server = subprocess.Popen(['python3', 'run', 'giftenoverzicht'], cwd=homedir)

elif True:
    def stop_server():
        global server
        server.terminate()


    def start_server():
        global server
        global exact_process, smtp_process

        # Delete the test database
        os.remove('overzichtgen.db')

        # Start the Exact simulator
        exact_process = subprocess.Popen('exact_sim.py', shell=True)
        smtp_process = subprocess.Popen(homedir+'/simulators/smtp.py', shell=True)

        # Set the configuration
        from admingen.clients.exact_rest import ExactClientConfig
        ecc = ExactClientConfig
        ecc().update({'base': 'http://localhost:8001'})

        #os.environ['PROJECTNAME'] = 'giftenoverzicht'

        import sys
        import threading
        sys.path.append(testdir+'..')
        from giftenoverzicht import run
        server = threading.Thread(target=run, args=(testdir,))
        server.setDaemon(True)
        server.start()

else:
    def stop_server():
        pass
    def start_server():
        pass


class SeleniumSimulatedTests(unittest.TestCase):
    """ Some tests depend on other tests having been completed. """
    smtp_defined = False
    org_defined = False

    @classmethod
    def setUpClass(cls):
        start_server()
        chromeOptions = webdriver.ChromeOptions()
        prefs = {"download.default_directory": downloaddir}
        chromeOptions.add_experimental_option("prefs", prefs)
        cls.browser = webdriver.Chrome(chrome_options=chromeOptions)
        cls.browser.implicitly_wait(10)  # seconds
        cls.browser.get('http://localhost:8080/gebruikers')
        login(cls.browser)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()

    def testCreateUser(self):
        browser = self.browser
        browser.get('http://localhost:8080/gebruikers')
        add_b = browser.find_element_by_class_name('btn-primary')
        # Check there is one and just one user
        self.assertEqual(len(browser.find_elements_by_tag_name('tr')), 1)
        # Click the Add button
        add_b.click()
        # Wait for the submit button
        submit = browser.find_element_by_tag_name('button')
        # Fill-in the details for the user
        details = {'name': 'ppuk',
                   'fullname': 'Pietje Puk',
                   'password': 'DitIsEenGeheim',
                   'password_shadow': 'DitIsEenGeheim',
                   'email': 'ppuk@godskerk.nl'}
        for k, v in details.items():
            input = browser.find_element_by_name(k)
            input.clear()
            input.send_keys(v)
        submit.click()
        # Wait for the Success screen
        el = browser.find_element_by_xpath("//div[contains(text(),'Success')]")
        # Go back to the user page
        browser.find_element_by_xpath("//a[contains(text(),'Gebruikers')]").click()
        # Wait for the Add User button
        add_b = browser.find_element_by_class_name('btn-primary')
        # Check there is an additional user
        self.assertEqual(len(browser.find_elements_by_tag_name('tr')), 2)

    def test1CreateOrginisation(self):
        browser = self.browser
        browser.get('http://localhost:8080/organisaties')
        add_b = browser.find_element_by_class_name('btn-primary')
        # Check there is are no organisations
        self.assertEqual(len(browser.find_elements_by_tag_name('tr')), 0)
        # Click the Add button
        add_b.click()
        # Wait for the submit button
        submit = browser.find_element_by_tag_name('button')
        # Fill-in the details for the user
        details = {'name': 'Lifeconnexion',
                   'description': 'Lifeconnexion, Amersfoort',
                   'mailfrom': 'Lifeconnexion <overzichten@lifeconnexion.nl>',
                   'gift_accounts': '8000 8050 8100 8150 8200 8800 8900 8990 8991 8105 8106 8998',
                   'template': '''.. header::

        .. image:: %(logo)s
          :height: 1cm
          :align: left

.. footer::  
  http://www.lifeconnexion.nl''',
                   'mail_body': '''### Beste gever, vragen kun je stellen aan: marloes@lifeconnexion.nl''',
                   'exact_division': '15972',
                   'admin_id': '102',
                   }
        for k, v in details.items():
            input = browser.find_element_by_name(k)
            input.clear()
            input.send_keys(v)
        submit.click()
        # Wait for the Success screen
        el = browser.find_element_by_xpath("//div[contains(text(),'Success')]")
        # Go back to the user page
        browser.find_element_by_xpath("//a[contains(text(),'Organisaties')]").click()
        # Wait for the Add User button
        add_b = browser.find_element_by_class_name('btn-primary')
        # Check there is an additional organisation
        self.assertEqual(len(browser.find_elements_by_tag_name('tr')), 1)
        # Investigate it
        browser.find_element_by_tag_name('tr').click()
        for k, v in details.items():
            el = browser.find_element_by_name(k)
            self.assertEqual(el.get_attribute("value"), v)

        SeleniumSimulatedTests.org_defined = True

    def testWorkflow(self):
        if not self.org_defined:
            self.test1CreateOrginisation()

        smtp.testmode = True

        shutil.copyfile('users.json', '1.users.json')
        shutil.copyfile('accounts.json', '1.accounts.json')
        shutil.copyfile('transactions.json', '1.transactions.json')

        smtp_details = SmtpDetails(1, 'testaccount', 'smtp://localhost:8025', 'ppuk', '----')
        Overzichten.smtp_data.add(**asdict(smtp_details))

        browser = self.browser
        browser.get('http://localhost:8080/')
        but = browser.find_element_by_class_name('btn-primary')
        but.click()

        # Ensure we are at step 1.
        el = browser.find_element_by_xpath("//a[contains(text(),'Stap 1:')]")
        el.click()

        # Now we should be able to enter the period details
        details = {'year': '2018',
                   'from': '2',
                   'until': 11}
        for k, v in details.items():
            input = browser.find_element_by_name(k)
            input.clear()
            input.send_keys(v)

        but = browser.find_element_by_xpath("//button")
        but.click()

        # Wait until the processing is done.
        xp = "//a[contains(text(),'Stap 4:') and contains(@class, 'btn-primary')]"
        start = time.time()
        while True:
            try:
                browser.get('http://localhost:8080/')
                _ = browser.find_element_by_xpath(xp)
                break
            except:
                assert time.time() - start < 60

        # We should have two lines in the list of givers.
        lines = list(browser.find_elements_by_xpath('//tbody/tr'))
        self.assertEqual(len(lines), 2)

        # Try to send an email
        el = browser.find_element_by_xpath("//a[contains(@href,'/versturen?file')]")
        el.click()

        # Wait until the email has been sent
        while not smtp.DummyClient.msgs:
            time.sleep(0.1)

        self.assertEqual(len(smtp.DummyClient.msgs), 1)

        # Try sending a batch
        smtp.DummyClient.msgs = []
        el = browser.find_element_by_class_name('btn-success')
        el.click()

        # Wait until the email has been sent
        start = time.time()
        while len(smtp.DummyClient.msgs) < 2:
            assert time.time() < start+1000
            time.sleep(0.1)

        # Check the contents of the two overzicht lines
        details = [['1553', 'Puk, Grietje', 'grietje.puk@hotmail.com', ' 123,55'],
                   ['1661', 'Puk, Pietje', '	pietje.puk@hotmail.com', ' 3.375,00']]
        for det, line in zip(details, lines):
            cols = list(browser.find_elements_by_xpath("//tr[@id='%s']/td"%line.id))
            for c, v in zip(cols, det):
                self.assertEqual(c, v)

        # Now try to download two reports
        for f in [name for name in os.listdir('downloads') \
                  if os.path.isfile(os.path.join('downloads', name))]:
            os.remove('downloads/' + f)

        links = list(browser.find_elements_by_xpath("//a[contains(text(),'pdf')]"))
        self.assertEqual(len(links), 2)
        for link in links:
            link.click()

        start = time.time()
        while nr_files('downloads') != 2:
            time.sleep(0.1)
            assert time.time() <  start + 10



def nr_files(d):
    return len([name for name in os.listdir(d) if os.path.isfile(os.path.join(d, name))])


def login(browser, user='test', pw='testingtesting'):
    n = browser.find_element_by_name('username')
    n.clear()
    n.send_keys(user)
    p = browser.find_element_by_name('password')
    p.clear()
    p.send_keys(pw)
    b = browser.find_element_by_tag_name('button')
    b.click()
