
import os
from datetime import datetime
import time
from decimal import Decimal
from selenium import webdriver
import csv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


from admingen.servers import Message
from admingen.keyring import KeyRing
from admingen.util import quitter, findNewFile, checkExists, DownloadError
from admingen.config import downloaddir
from admingen.db_api import DbTable, sessionScope, Required, Set, select, Optional


@Message
class ZekeDetails:
    url: str = ''
    username: str = ''


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



@DbTable
class ZekeAccount:
    url: str
    username: str
    transactions: Set('ZekeTransaction')

@DbTable
class ZekeTransaction:
    account: Required(ZekeAccount, index=True)
    order_nr: Required(int, index=True, unique=True)
    timestamp: datetime
    herkomst: str
    valuta: str
    gross: Decimal
    tax: Decimal
    countrycode: str
    btwcode: Optional(str, nullable=True)


def readTransactions(fnames, details: ZekeDetails):
    # First read the details of ICP transactions.
    # These records have additional data for those transactions
    icp_transactions = {}
    if fnames[0]:
        # There are no ICP transactions during the period
        with open(fnames[0], newline='') as f:
            reader = csv.reader(f, delimiter=',')
            _ = next(reader)   # Skip the first line
            icp_transactions = {t[0]:t for t in reader}

    # Now handle the non-icp transactions
    fname = fnames[1]
    if fname is None:
        # There are no transactions to download
        return
    with open(fname, newline='') as f:
        reader = csv.reader(f, delimiter=',')
        _ = next(reader)  # Skip the first line
        transactions = list(reader)

    with sessionScope():
        # Find the account for these transactions
        account = select(a for a in ZekeAccount \
                                if a.url == details.url and a.username == details.username).first()
        # Retrieve all the existing transactions that we have data for
        existing = select(t for t in ZekeTransaction if t.account==account)
        existing = {t.order_nr:t for t in existing}

        # Process all new transaction details
        for transactie in transactions:
            td = {k:transactie[v] for k, v in {'order_nr':2,
                                               'herkomst':3,
                                               'valuta':4,
                                               'countrycode':10}.items()}
            td['timestamp'] = datetime.strptime(transactie[1], '%d-%m-%Y')
            td['account'] = account
            td['gross'] = Decimal('.'.join(transactie[5:7]))
            td['tax'] = Decimal('.'.join(transactie[7:9]))
            if transactie[0] in icp_transactions:
                icp = icp_transactions[transactie[0]]
                td['btwcode'] = icp[10]
                assert Decimal('.'.join(icp[4:6])) == td['gross']
                assert Decimal('.'.join(icp[6:8])) == td['tax']
            else:
                td['btwcode'] = None

            # Try if there is already a record for this order
            if td['order_nr'] in existing:
                t = existing[td['order_nr']]
                # If non-zero, update the financials
                if td['gross'] != Decimal('0.0'):
                    # Check the original financials were unset
                    assert t.gross == Decimal('0.0')
                    assert t.tax == Decimal('0.0')
                    t.gross = td['gross']
                    t.tax = td['tax']
            else:
                # Add a new transaction
                existing[td['order_nr']] = ZekeTransaction(**td)


def loadTransactions(start: datetime, end: datetime, details: ZekeDetails):
    """ Load the transactions as seen by Zeke into the database. """
    # First get the ICP transactions
    # ICP transactions hold additional information for certain transactions
    fnames = [downloadTransactions(start, end, details, icp) for icp in [True, False]]
    readTransactions(fnames, details)
