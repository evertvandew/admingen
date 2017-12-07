"""
Interface to PayPal

The PayPal API SUCKS bigtime, so we use web scraping to download the transaction details.
"""
from decimal import Decimal
import datetime
import os.path
import time
import shutil
from csv import DictReader
from contextlib import contextmanager
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from admingen.config import getConfig

EU_COUNTRY_CODES = ['BE', 'BG', 'CY', 'DK', 'DU', 'EE', 'FI', 'FR', 'GR', 'HU', 'IE', 'IT', 'HR',
                    'LV', 'LT', 'LU', 'MT', 'NL', 'AT', 'PL', 'PT', 'RO', 'SI', 'SK', 'ES', 'CZ',
                    'GB', 'SE']

DOWNLOAD_DIR = getConfig('paypalclient.downloaddir', os.getcwd() + '/downloads')
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def login(browser, username, password):
    """ Login to the PayPal reports page """
    browser.get('https://business.paypal.com/merchantdata/reportHome')

    # fill in the login details
    elem = browser.find_element_by_name("login_email")
    elem.send_keys(username)

    elem = browser.find_element_by_name("login_password")
    elem.send_keys(password)

    # Submit the details
    elem = browser.find_element_by_name("btnLogin")
    elem.click()


def wait_till_loaded(browser):
    wait = WebDriverWait(browser, 20)
    wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "loading")))


def generateReport(browser, range_value):
    # Set the correct filters
    filters = browser.find_elements_by_class_name("filters")
    # Set the range filter to 'yesterday'
    range = [f for f in filters if 'dateRange' in f.get_attribute('class')][0]
    btn = range.find_element_by_tag_name('button')
    btn.click()
    a = range.find_element_by_xpath('//a[@data-id="%s"]' % range_value)
    a.click()
    # Set the type 'all transactions'
    txntype = [f for f in filters if 'txnType' in f.get_attribute('class')][0]
    btn = txntype.find_element_by_tag_name('button')
    btn.click()
    a = range.find_element_by_xpath('//a[@data-value=""]')
    a.click()

    # Generate the report
    submit = [f for f in filters if 'createBtn' in f.get_attribute('class')][0]
    submit.click()


def checkReportAvailable(browser, daterange):
    """ Returns the element describing the daterange in a downloadable report, or None """
    # Check if the right line is available
    div = None
    while not div:
        try:
            div = browser.find_element_by_id('pastHistory')
        except:
            time.sleep(0.1)
    e = div.find_elements_by_xpath('//td[contains(text(), "%s")]' % daterange)
    if e:
        # The report is available
        return e[0]


def downloadTransactions(username, password, range_value='YESTERDAY') -> str:
    """ Download the transactions for yesterday. Returns the filename of the download """

    @contextmanager
    def quitter(item):
        """ Make sure the item is 'quit' """
        try:
            yield
        finally:
            item.quit()

    chromeOptions = webdriver.ChromeOptions()
    prefs = {"download.default_directory": DOWNLOAD_DIR}
    chromeOptions.add_experimental_option("prefs", prefs)
    browser = webdriver.Chrome(chrome_options=chromeOptions)

    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(1)
    daterange = yesterday.strftime('%d %b. %Y - %d %b. %Y').lower()

    # browser = webdriver.Chrome()
    with quitter(browser):
        login(browser, username, password)

        # Wait until the website is loaded
        wait_till_loaded(browser)

        # Navigate to the 'Download History' part of the page
        elem = WebDriverWait(browser, 20).until(
            EC.presence_of_element_located((By.ID, "dlogNav"))
        )
        elem.click()
        time.sleep(0.1)
        wait_till_loaded(browser)

        e = checkReportAvailable(browser, daterange)

        if not e:
            generateReport(browser, range_value)

        # Wait until the report is available
        start = time.time()
        while True:
            elem = browser.find_element_by_class_name('dlogRefreshList')
            elem.click()
            wait_till_loaded(browser)
            # Wait 10 minutes for the correct line
            if time.time() - start > 10 * 60:
                raise RuntimeError('Report did not arrive in time')
            e = checkReportAvailable(browser, daterange)
            if e:
                break

        # First make a snapshot of the files in the download directory
        files = os.listdir(DOWNLOAD_DIR)

        # Download the desired report
        p = e.find_element_by_xpath('..')
        b = p.find_element_by_tag_name('button')
        b.click()

        # Wait until a new CSV file appears
        start = time.time()
        while True:
            time.sleep(0.1)
            # This is safe, because Chrome will only rename the file to its final name when complete
            new_files = [f for f in os.listdir(DOWNLOAD_DIR) if
                         f not in files and f.lower().endswith('.csv')]
            if new_files:
                return os.path.join(DOWNLOAD_DIR, new_files[0])
            # Wait at most 5 minutes until the download is complete
            if time.time() - start > 5 * 60:
                raise RuntimeError('Download not complete in time')


def myopen(fname):
    """ File open that tests a number of encodings.
        Necessary for reading PayPal CSV files, as they use the MickeySoft-invented utf-8-sig
        encoding instead of regular utf-8.
    """
    for enc in ['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be']:
        try:
            with open(fname, encoding=enc) as f:
                s = f.read(10)
            if s[0] in ['"', 'D']:
                return open(fname, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise RuntimeError('Could not find correct encoding')



def pp_reader(fname):
    """ Generator that yields paypal transactions """
    # check if fname is a string or a file-like object
    if isinstance(fname, str):
        reader = DictReader(myopen(fname), delimiter=',', quotechar='"')
    else:
        reader = DictReader(fname, delimiter=',', quotechar='"')
    # The only thing wrong with reader is that the numbers are strings, not numbers,
    # and the date is a string, not a datetime.
    for line in reader:
        for key in ['Bruto', 'Fee', 'Net', 'Sales Tax', 'Saldo']:
            s = line[key]
            # For conversion to Decimal, first get rid of periods, then swap comma's with periods
            s = s.replace('.', '')
            s = s.replace(',', '.')
            line[key] = Decimal(s, ) if s else Decimal('0.00')
        line['Datum'] = datetime.datetime.strptime(line['Datum'], '%d-%m-%Y')
        yield line
