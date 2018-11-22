
import os
from datetime import datetime
import time
from decimal import Decimal
from selenium import webdriver
import csv
from typing import List
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


from admingen.servers import Message
from admingen.keyring import KeyRing
from admingen.util import quitter, findNewFile, checkExists, DownloadError
from admingen.config import downloaddir
from admingen.db_api import DbTable, sessionScope, Required, Set, select, Optional
from admingen.international import SalesType, ISO_EU_COUNTRY_CODES
from dataclasses import dataclass


@dataclass
class ZekeDetails:
    url: str = ''
    username: str = ''

@dataclass
class ZekeSecrets:
    password: str = ''



def downloadTransactions(start: datetime, end: datetime, details: ZekeDetails,
                    icp: bool):
    checkExists(downloaddir)
    kc = KeyRing.theKeyring
    assert kc is not None
    chromeOptions = webdriver.ChromeOptions()
    prefs = {"download.default_directory": downloaddir}
    chromeOptions.add_experimental_option("prefs", prefs)

    browser = webdriver.Chrome(chrome_options=chromeOptions)
    with quitter(browser):
        def checkFunc():
            """ Predicate to check if downloading goes all-right.
                Return True if we continue to wait for the download.
            """
            # Check if an error was reported, e.g. because there are no records to download
            errs = browser.find_elements_by_class_name('alert')
            err = [e for e in errs if 'geen gegevens' in e.text]
            return not err or all(not e.is_displayed for e in err)
        browser.get('%s/admin/#/stats/export'%details.url)

        # Fill-in the login form
        elem = browser.find_element_by_name("loginname")
        elem.send_keys(details.username)
        elem = browser.find_element_by_name("password")
        elem.send_keys(kc[details.username])
        elem = browser.find_element_by_name("submit")
        elem.click()
        time.sleep(1)
        browser.get('%s/admin/#/stats/export' % details.url)
        time.sleep(2)
        # Choose to view regular or ICP sales
        sel = browser.find_element_by_xpath('//select[@ng-model="view.data"]')
        sel.click()
        choice = 'icp' if icp else 'invoices'
        opt = sel.find_element_by_xpath('//option[@value="%s"]'%choice)
        opt.click()
        # Start to set the date range to inquire after
        el = browser.find_element_by_xpath('//input[@ng-model="view.datepicker.date"]')
        el.click()
        # Get the available options
        els = browser.find_elements_by_xpath('//li[@data-range-key]')
        # The first one is supposed to be the 'Afgelopen 7 dagen' option. Click it.
        el = els[0]
        assert el.text == 'Afgelopen 7 dagen'
        el.click()
        # Give it one second
        time.sleep(1)
        # Then download the data set
        files = os.listdir(downloaddir)
        el = browser.find_element_by_xpath('//a[@ng-click="view.downloadCSV()"]')
        el.click()

        try:
            return findNewFile(downloaddir, files, '.csv', checkFunc)
        except DownloadError:
            return None


class ZekeClassifier:
    def __init__(self):
        @DbTable
        class ZekeTransaction:
            order_nr: Required(int, index=True)   # The order number is what is referred to in PayPal
            timestamp: datetime
            herkomst: str
            valuta: str
            gross: Decimal
            tax: Decimal
            countrycode: str
            btwcode: Optional(str, nullable=True)
        self.ZekeTransaction = ZekeTransaction

    def readTransactions(self, icp_fnames: List[str], transactions: List[str], details: ZekeDetails):
        # First read the details of ICP transactions.
        # These records have additional data for those transactions
        icp_transactions = {}
        for fname in icp_fnames:
            # There are ICP transactions during the period
            with open(fname, newline='') as f:
                reader = csv.DictReader(f, delimiter=';')
                icp_transactions.update({t['Order ID']:t for t in reader})

        # Now handle the non-icp transactions
        reg_transactions = []
        for fname in transactions:
            with open(fname, newline='') as f:
                reader = csv.DictReader(f, delimiter=';')
                reg_transactions.extend(list(reader))

        # Retrieve all the existing transactions that we have data for
        existing = select(t for t in self.ZekeTransaction)
        existing = {t.order_nr:t for t in existing}

        # Process all new transaction details
        for transactie in reg_transactions:
            td = {k:transactie[v] for k, v in {'order_nr':'Order ID',
                                               'herkomst':'Herkomst',
                                               'valuta':'Valuta',
                                               'countrycode':'Land factuuradres'}.items()}
            td['timestamp'] = datetime.strptime(transactie['Factuurdatum'], '%d-%m-%Y')

            gross = Decimal(transactie['Totaalbedrag incl. BTW'].replace(',', '.'))
            tax = Decimal(transactie['Totaal BTW-bedrag'].replace(',', '.'))
            if transactie['Order ID'] in icp_transactions:
                icp = icp_transactions[transactie['Order ID']]
                td['btwcode'] = icp['BTW-nummer klant']
            else:
                td['btwcode'] = None

            if transactie['Order ID'] in existing:
                print ('Overwriting existing transaction')
                existing_zt = existing[transactie['Order ID']]

                existing_zt.gross = gross
                existing_zt.tax = tax

            else:
                td['gross'] = gross
                td['tax'] = tax

                # Add a new transaction
                new_zt = self.ZekeTransaction(**td)
                existing[td['order_nr']] = new_zt



    def loadTransactions(self, start: datetime, end: datetime, details: ZekeDetails):
        """ Load the transactions as seen by Zeke into the database. """
        # First get the ICP transactions
        # ICP transactions hold additional information for certain transactions
        fnames = [downloadTransactions(start, end, details, icp) for icp in [True, False]]
        self.readTransactions(fnames, details)


    def classifySale(self, order_nr):
        with sessionScope():
            t = select(t for t in self.ZekeTransaction if t.order_nr==order_nr).first()
            if t is None:
                return SalesType.Unknown
            if t.countrycode.upper() == 'NL':
                return SalesType.Local
            if t.countrycode.upper() in ISO_EU_COUNTRY_CODES:
                if t.btwcode:
                    return SalesType.EU_ICP
                return SalesType.EU_private
            return SalesType.Other

    def getBtwAccount(self, order_nr):
        with sessionScope():
            t = select(t for t in self.ZekeTransaction if t.order_nr==order_nr).first()
            if t is None:
                return None
            return t.btwcode
