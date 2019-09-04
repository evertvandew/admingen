"""
Interface to PayPal

The PayPal API SUCKS bigtime, so we use web scraping to download the transaction details.
"""
from decimal import Decimal
import datetime
import os.path
import time
import shutil
import enum
from csv import DictReader
from admingen.util import quitter, findNewFile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

from admingen.config import getConfig, downloaddir
from dataclasses import dataclass, fields, asdict


DataRangesString = ['TODAY', 'YESTERDAY', 'LAST_MONTH', 'LAST_3_MONTHS', 'LAST_6_MONTHS', 'CUSTOM']

DataRanges = enum.Enum('DataRanges', DataRangesString)

@dataclass
class PaypalSecrets:
    username: str
    password: str


def login(browser, details: PaypalSecrets):
    """ Login to the PayPal reports page """
    browser.get('https://business.paypal.com/merchantdata/reportHome')

    # fill in the login details
    elem = browser.find_element_by_name("login_email")
    elem.send_keys(details.username)

    elem = browser.find_element_by_name("login_password")
    if not elem.is_displayed():
        elem = browser.find_element_by_name("btnNext")
        elem.click()
        elem = browser.find_element_by_name("login_password")
        while not elem.is_displayed():
            time.sleep(0.1)
    elem.send_keys(details.password)

    # Submit the details
    elem = browser.find_element_by_name("btnLogin")
    elem.click()


def wait_till_loaded(browser):
    wait = WebDriverWait(browser, 20)
    wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "loading")))


def generateReport(browser, range_value: str):
    """ Only the pre-defined ranges are currently supported """
    # Set the correct filters
    # First wait until they are available
    while True:
        filters = browser.find_elements_by_class_name("filters")
        # Set the range filter to 'yesterday'
        range = [f for f in filters if 'dateRange' in f.get_attribute('class')][0]
        btn = range.find_element_by_tag_name('button')
        if btn:
            btn.click()
            break
        time.sleep(2)
    filter_range = range_value.upper() if not '/' in range_value else 'CUSTOM'
    a = range.find_element_by_xpath('//a[@data-id="%s"]' % filter_range)
    a.click()
    # For the CUSTOM range, explicitly set the 'from' and 'to' fields
    if filter_range == 'CUSTOM':
        start, finish = period2dt(range_value)
        for field_text, value in [('From', start), ('To', finish)]:
            e = a.find_element_by_xpath('//label[contains(text(), "%s")]' % field_text)
            element = WebDriverWait(e.parent, 3).until(
                EC.visibility_of_element_located((By.TAG_NAME, 'input')))
            element.send_keys(value.strftime('%d/%m/%Y'))


    # Set the type 'all transactions'
    txntype = [f for f in filters if 'txnType' in f.get_attribute('class')][0]
    btn = txntype.find_element_by_tag_name('button')
    btn.click()
    a = range.find_element_by_xpath('//a[@data-value=""]')
    a.click()

    # Generate the report
    submit = [f for f in filters if 'createBtn' in f.get_attribute('class')][0]
    submit.click()


def checkReportAvailable(browser, dateranges):
    """ Returns the element describing the daterange in a downloadable report, or None """
    # Check if the right line is available
    div = None
    while not div:
        try:
            div = browser.find_element_by_id('pastHistory')
        except:
            time.sleep(0.1)
    for daterange in dateranges:
        try:
            e = div.find_element_by_xpath('//td[contains(text(), "%s")]' % daterange)
            # The report is in the list; check it can be downloaded.
            p = e.find_element_by_xpath('..')
            _ = p.find_element_by_tag_name('button')
            # The report can be downloaded.
            return e
        except NoSuchElementException:
            # Try the next daterange
            pass
    return



def period2dt(range_value: DataRanges=DataRanges.YESTERDAY):
    """ Rangevalue is either a DataRange value, or a string.
        The string must have the format yyyy/mm/dd-yyyy/mm/dd
    """
    if isinstance(range_value, str) and range_value[0].isnumeric():
        return tuple(datetime.datetime.strptime(s, '%Y/%m/%d').date() for s in range_value.split('-'))
    today = datetime.datetime.now().date()
    if range_value == DataRanges.TODAY:
        return today, today
    elif range_value == DataRanges.YESTERDAY:
        yesterday = today - datetime.timedelta(1)
        return yesterday, yesterday
    elif range_value == DataRanges.CUSTOM:
        raise ValueError('Custom range not supported--use a string')
    else:
        end = datetime.date(today.year, today.month, 1) - datetime.timedelta(1)
        sy = today.year
        if range_value == DataRanges.PASTMONTH:
            sm = today.month - 1
        elif range_value == DataRanges.PAST3MONTHS:
            sm = today.month - 3
        elif range_value == DataRanges.PAST6MONTHS:
            sm = today.month - 6
        if sm < 1:
            sy -= 1
            sm += 12
        start = datetime.datetime(sy, sm, 1).date()
    return start, end



def downloadTransactions(secrets: PaypalSecrets, range_value: DataRanges=DataRanges.YESTERDAY) -> str:
    """ Download the transactions for yesterday. Returns the filename of the download """
    chromeOptions = webdriver.ChromeOptions()
    prefs = {"download.default_directory": downloaddir}
    chromeOptions.add_experimental_option("prefs", prefs)
    browser = webdriver.Chrome(chrome_options=chromeOptions)
    #browser.implicitly_wait(20)  # seconds

    dateranges = []
    # Paypal -- bless their darling hearts -- have two (known) formats for date ranges.
    txts = tuple(d.strftime('%d %b %Y') for d in period2dt(range_value))
    daterange = '%s - %s' % txts
    dateranges.append(daterange)
    txts = tuple(d.strftime('%d %b. %Y').lower() for d in period2dt(range_value))
    daterange = '%s - %s' % txts
    dateranges.append(daterange)

    # browser = webdriver.Chrome()
    with quitter(browser):
        login(browser, secrets)

        # Wait until the website is loaded
        wait_till_loaded(browser)

        # Navigate to the 'Download History' part of the page
        elem = WebDriverWait(browser, 20).until(
            EC.presence_of_element_located((By.ID, "dlogNav"))
        )
        elem.click()
        time.sleep(0.1)
        wait_till_loaded(browser)

        e = checkReportAvailable(browser, dateranges)

        if not e:
            generateReport(browser, range_value)

        # Wait until the report is available
        start = time.time()
        while True:
            try:
                elem = browser.find_element_by_class_name('dlogRefreshList')
                if elem:
                    time.sleep(0.5)
                    elem.click()

                time.sleep(5)
                wait_till_loaded(browser)
                # Wait 10 minutes for the correct line
                if time.time() - start > 10 * 60:
                    raise RuntimeError('Report did not arrive in time')
                e = checkReportAvailable(browser, dateranges)
                if e:
                    break
            except:
                time.sleep(1)

        # First make a snapshot of the files in the download directory
        files = os.listdir(downloaddir)

        # Download the desired report
        p = e.find_element_by_xpath('..')
        b = p.find_element_by_tag_name('button')
        b.click()

        return findNewFile(downloaddir, files, '.csv')


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


@dataclass
class PPTransactionDetails:
    Datum: str
    Tijd: str
    Tijdzone: str
    Naam: str
    Type: str
    Status: str
    Valuta: str
    Bruto: Decimal
    Fee: Decimal
    Net: Decimal
    Vanemailadres: str
    Naaremailadres: str
    Transactiereferentie: str
    Verzendadres: str
    Statusadres: str
    ArtikelNaam: str
    ArtikelNr: str
    Verzendkosten: str
    Verzekeringsbedrag: str
    SalesTax: str
    Naamoptie1: str
    Waardeoptie1: str
    Naamoptie2: str
    Waardeoptie2: str
    ReferenceTxnID: str
    Factuurnummer: str
    CustomNumber: str
    Hoeveelheid: str
    Ontvangstbewijsreferentie: str
    Saldo: str
    Adresregel1: str
    Adresregel2regioomgeving: str
    Plaats: str
    StaatProvincieRegioGebied: str
    ZipPostalCode: str
    Land: str
    Telefoonnummercontactpersoon: str
    Onderwerp: str
    Note: str
    Landcode: str
    Effectopsaldo: str


type_translations = {'General Currency Conversion': 'Algemeen valutaomrekening',
                     'Payment Refund': 'Terugbetaling'}

def pp_reader(fname):
    """ Generator that yields paypal transactions """
    # check if fname is a string or a file-like object

    file = myopen(fname) if isinstance(fname, str) else fname

    with file as f:
        reader = DictReader(f, delimiter=',', quotechar='"')

        # PP uses different key names depending on the language of the UI
        # Ensure the Dutch names are used
        english = 'Gross' in reader.fieldnames
        reader.fieldnames = 'Datum,Tijd,Tijdzone,Naam,Type,Status,Valuta,Bruto,Fee,Net,Van e-mailadres,Naar e-mailadres,Transactiereferentie,Verzendadres,Status adres,ArtikelNaam,ArtikelNr,Verzendkosten,Verzekeringsbedrag,Sales Tax,Naam optie 1,Waarde optie 1,Naam optie 2,Waarde optie 2,Reference Txn ID,Factuurnummer,Custom Number,Hoeveelheid,Ontvangstbewijsreferentie,Saldo,Adresregel 1,Adresregel 2/regio/omgeving,Plaats,Staat/Provincie/Regio/Gebied,Zip/Postal Code,Land,Telefoonnummer contactpersoon,Onderwerp,Note,Landcode,Effect op saldo'.split(',')

        allfields = [f.name for f in fields(PPTransactionDetails)]
        # Paypal uses some characters in keys that mess-up XML: get rid of them.
        # I already said I don't like XML, didn't I?
        translator = str.maketrans({' ':None, '-':None, '/':None, })
        keys = [(k.translate(translator), k) for k in reader.fieldnames]
        keys = [(k1, k2) for k1, k2 in keys if k1 in allfields]

        # The only thing wrong with reader is that the numbers are strings, not numbers,
        # and the date is a string, not a datetime.
        for line in reader:
            for key in ['Bruto', 'Fee', 'Net', 'Sales Tax', 'Saldo']:
                s = line[key]
                if english:
                    # Remove the thousands separator
                    s = s.replace(',', '')
                else:
                    # For conversion to Decimal, first get rid of periods, then swap comma's with periods
                    s = s.replace('.', '')
                    s = s.replace(',', '.')
                line[key] = Decimal(s, ) if s else Decimal('0.00')
            if '-' in line['Datum']:
                line['Datum'] = datetime.datetime.strptime(line['Datum'], '%d-%m-%Y')
            elif '/' in line['Datum']:
                line['Datum'] = datetime.datetime.strptime(line['Datum'], '%d/%m/%Y')

            line['Type'] = type_translations.get(line['Type'], line['Type'])
            # Strip keys from illegal element characters and unused elements
            line = {k1:line[k2] for k1, k2 in keys}

            transaction = PPTransactionDetails(**line)

            yield transaction
