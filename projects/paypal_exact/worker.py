"""



Documentation PayPal API:
https://developer.paypal.com/docs/classic/api/apiCredentials/#credential-types
PayPal SDK (nieuw) : https://github.com/paypal/PayPal-Python-SDK


"""
import time
import asyncio
import datetime
from collections import namedtuple
import os
from decimal import Decimal, ROUND_HALF_UP
import traceback
from enum import IntEnum
from typing import List
from pony import orm

import paypalrestsdk
from paypalrestsdk.payments import Payment
from admingen.servers import mkUnixServer, Message, expose
from admingen.keyring import KeyRing
from admingen.email import sendmail
from admingen import config
from admingen.clients.rest import OAuth2
from admingen.clients.paypal import downloadTransactions, pp_reader, EU_COUNTRY_CODES
from admingen import logging
from admingen.db_api import the_db


@Message
class paypallogin:
    administration: int
    paypal_client_id: str
    client_password: str
    client_cert: bytes


@Message
class exactlogin:
    administration: int
    client_id: str
    client_secret: str
    client_token: str


@Message
class taskdetails:
    administration: int
    paypalbook: int

@config.configtype
class mailconfig:
    adminmail='evert.vandewaal@xs4all.nl'
    appname='Paypal Exporter'
    keyring='paypalreaderring.enc'
    readersock='paypalreader.sock'


appconfig = mailconfig()

bootmail = '''I have restarted, and need my keyring unlocked!

Your faithful servant, {appconfig.appname}'''

if False:
    # First let the maintainer know we are WAITING!
    sendmail(config['adminmail'], config['selfmail'],
             'Waiting for action',
             bootmail % config['appname'])

ExactTransaction = namedtuple('ExactTransaction', ['date', 'ledger', 'lines', 'closingbalance'])
ExactTransactionLine = namedtuple('ExactTransactionLine',
                                  ['GLAccount', 'GLType', 'Description', 'Amount', 'ForeignAmount',
                                   'ForeignCurrency', 'ConversionRate', 'additional'])
WorkerConfig = namedtuple('WorkerConfig',
                          ['ledger', 'costs_account', 'pp_account', 'sale_account_nl', 'sale_account_eu_no_vat', 'sale_account_world',
                           'purchase_account_nl', 'purchase_account_eu_no_vat', 'purchase_account_world', 'pp_kruispost', 'vat_account'])


# Create a cache for storing the details of earlier transactions
db = the_db
class TransactionLog(db.Entity):
    timestamp = orm.Required(datetime.datetime)
    pp_tx = orm.Required(str)
    vat_percent = orm.Required(Decimal)
    account = orm.Required(int)

db.bind(provider='sqlite', filename='transaction_cache.db', create_db=True)
db.generate_mapping(create_tables=True)

# TODO: Periodically clean up the cache


class GLAccountTypes(IntEnum):
    Cash = 10
    Bank = 12
    CreditCard = 14
    PaymentService = 16
    AccountsReceivable = 20
    AccountsPayable = 22
    VAT = 24
    EmployeesPayable = 25
    PrepaidExpenses = 26
    AccruedExpenses = 27
    IncomeTaxPayable = 29
    FixedAssets = 30
    OtherAssets = 32
    AccumulatedDeprecations = 35
    Inventory = 40
    CapitalStock = 50
    RetainedEarnings = 52
    LongTermDebt = 55
    CurrentPortionofDebt = 60
    General = 90
    SalesTaxPayable = 100
    Revenue = 110
    CostOfGoods = 111
    OtherCosts = 120
    SalesMarketingGeneralExpenses = 121
    DepreciationCosts = 122
    ResearchAndDevelopment = 123
    EmployeeCosts = 125
    LaborCosts = 126
    ExceptionalCosts = 130
    ExceptionalIncome = 140
    IncomeTaxes = 150
    InterestIncome = 160


class GLTransactionTypes(IntEnum):
    OpeningBalance = 10
    SalesEntry = 20
    SalesCreditNote = 21
    SalesReturnInvoice = 22
    PurchaseEntry = 30
    PurchaseCreditNote = 31
    PurchaseReturnInvoice = 32
    CashFlow = 40
    VATReturn = 50
    AssetDepreciation = 70



LineTemplate = '''            <GLTransactionLine type="40" line="{linenr}" status="20">
                <Date>{date}</Date>
                <FinYear number="{year}" />
                <FinPeriod number="{period}" />
                <GLAccount code="{GLAccount}" type="{GLType}" />
                {additional}
                <Description>{Description}</Description>
                <Amount>
                    <Currency code="EUR" />
                    <Value>{Amount}</Value>
                </Amount>
                <ForeignAmount>
                    <Currency code="EUR" />
                    <Value>{Amount}</Value>
                    <Rate>1</Rate>
                </ForeignAmount>
            </GLTransactionLine>'''


def generateExactLine(transaction: ExactTransaction, line: ExactTransactionLine, linenr):
    index = transaction.lines.index(line)
    nr_lines = len(transaction.lines)
    date = transaction.date.strftime('%Y-%m-%d')
    year = transaction.date.strftime('%Y')
    period = transaction.date.strftime('%m')
    return LineTemplate.format(**locals(), **line._asdict())


TransactionTemplate = '''        <GLTransaction>
            <TransactionType number="40" />
            <Journal code="{ledger}" type="12" />
{transactionlines}
        </GLTransaction>'''

FileTemplate = '''<?xml version="1.0" encoding="utf-8"?>
<eExact xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="eExact-XML.xsd">
    <GLTransactions>
{transactions}
    </GLTransactions>
</eExact>
'''

def generateExactTransaction(transaction: ExactTransaction):
    transactionlines = '\n'.join([generateExactLine(transaction, line, int((count+2)/2)) \
                                  for count, line in enumerate(transaction.lines)])
    return TransactionTemplate.format(**locals(), **transaction._asdict())


def generateExactTransactionsFile(transactions: List[ExactTransaction]):
    transactions = [generateExactTransaction(t) for t in transactions]
    return FileTemplate.format(transactions = '\n'.join(transactions))


class Region(IntEnum):
    NL = 1
    EU = 2
    World = 3
    Unknown = 4


class PaypalExactTask:
    """ Produce exact transactions based on the PayPal transactions """

    def __init__(self, pp_login, config: WorkerConfig, exact_token):
        self.pp_login, self.config, self.exact_token = pp_login, config, exact_token
        self.sale_accounts = {Region.NL: self.config.sale_account_nl,
                              Region.EU: self.config.sale_account_eu_no_vat,
                              Region.World: self.config.sale_account_world,
                              Region.Unknown: self.config.sale_account_nl}
        self.purchase_accounts = {Region.NL: self.config.purchase_account_nl,
                              Region.EU: self.config.purchase_account_eu_no_vat,
                              Region.World: self.config.purchase_account_world,
                                  Region.Unknown: self.config.purchase_account_nl}
        self.vat_percentages = {Region.NL: Decimal('0.21'),
                                Region.EU: Decimal('0.00'),
                                Region.World: Decimal('0.00'),
                                Region.Unknown: Decimal('0.21')}

    def determineAccountVat(self, transaction):
        """ Determine the grootboeken to be used for a specific transaction """

        if transaction['Type'] == 'Algemene opname':
            # A bank withdrawl goes to the kruispost
            return self.config.pp_kruispost, Decimal('0.00')

        # Determine if the transaction is within the Netherlands, the EU or the world.
        if transaction['Landcode'] == 'NL':
            region = Region.NL
        elif transaction['Landcode'] in EU_COUNTRY_CODES:
            region = Region.EU
        elif transaction['Landcode']:
            region = Region.World
        else:
            region = Region.Unknown


        accounts = self.sale_accounts if transaction['Net'] > 0 else self.purchase_accounts
        if transaction['Reference Txn ID']:
            # This is related to another payment, in almost all cases a return of a previous payment
            # If available, use the details from the previous transaction
            with orm.db_session():
                txs = orm.select(_ for _ in TransactionLog if _.pp_tx == transaction['Reference Txn ID'])
                for tx in txs:
                    return tx.account, tx.vat_percent
            # Transaction unknown, try to guess the details
            # This means that debtors and creditors are reversed
            accounts = self.sale_accounts if transaction['Net'] < 0 else self.purchase_accounts

        return accounts[region], self.vat_percentages[region]


    def determineComment(self, transaction):
        """ Determine the comment for a specific transaction """
        parts = [('ref:%s', transaction['Transactiereferentie']),
                 ('Fact: %s', transaction['Factuurnummer']),
                 ('%s', transaction['Note'])
                 ]
        if transaction['Valuta'] != 'EUR':
            parts.append(('%s', transaction['Valuta']))
            parts.append(('%s', transaction['Bruto']))
        parts = [a%b for a, b in parts if b]
        return ' '.join(parts)

    def make_transaction(self, transaction, rate=1):
        """ Translate a PayPal transaction into a set of Exact bookings
            :param rate: euro_amount / foreign_amount
        """
        # A regular payment in euro's
        gb_sales, vat_percentage = self.determineAccountVat(transaction)
        comment = self.determineComment(transaction)

        # Use the following sequence:
        # First booking: the VAT return on the transaction fee (if any)
        # Second booking: the transaction fee (without VAT)
        # Third booking: the actual sale
        # Fourth booking: the VAT on the sale

        foreign_valuta = transaction['Valuta']

        # Cache the results
        with orm.db_session():
            c = TransactionLog(timestamp=)
            txs = orm.select(_ for _ in TransactionLog if _.pp_tx == transaction['Reference Txn ID'])
            for tx in txs:
                return tx.account, tx.vat_percent

        lines = []
        if transaction['Fee']:
            # Assume that PayPal always imposes 21% VAT on its transaction fee.
            net, vat = [(transaction['Fee'] * Decimal(p)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) for p in ['0.79', '0.21']]
            net_euro, vat_euro = [(x*rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) for x in [net, vat]]
            # The VAT over the fee
            lines.append((self.config.vat_account, GLAccountTypes.General,
                         comment,
                         -vat_euro, -vat, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account))
            lines.append((self.config.pp_account, GLAccountTypes.Bank,
                          comment,
                          vat_euro, vat, foreign_valuta, rate,
                          ''))
            # The actual fee
            lines.append((self.config.costs_account, GLAccountTypes.SalesMarketingGeneralExpenses,
                         comment,
                          -net_euro, -net, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account))
            lines.append((self.config.pp_account, GLAccountTypes.Bank,
                          comment,
                          net_euro, net, foreign_valuta, rate,
                          ''))

        # The actual sale
        net, vat = [(transaction['Bruto'] * p).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) for p in [1-vat_percentage, vat_percentage]]
        net_euro, vat_euro = [(x * rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) for x in
                              [net, vat]]
        lines.append((gb_sales, GLAccountTypes.Revenue,
                         comment,
                      -net_euro, -net, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account))
        lines.append((self.config.pp_account, GLAccountTypes.Bank,
                         comment,
                      net_euro, net, foreign_valuta, rate,
                         ''))

        # The VAT over the sale
        if vat_euro != Decimal('0.00'):
            lines.append((self.config.vat_account, GLAccountTypes.General,
                          comment,
                          -vat_euro, -vat, foreign_valuta, rate,
                             '<GLOffset code="%s" />'%self.config.pp_account))
            lines.append((self.config.pp_account, GLAccountTypes.Bank,
                          comment,
                          vat_euro, vat, foreign_valuta, rate,
                             ''))

        lines = [ExactTransactionLine(*l) for l in lines]

        exact_transaction = ExactTransaction(transaction['Datum'], self.config.ledger, lines,
                                       transaction['Saldo'])
        return exact_transaction

    def make_foreign_transaction(self, transactions):
        # Get the details from the original transaction
        sale = next(t for t in transactions if
                    t['Type'] != 'Algemeen valutaomrekening' and t['Valuta'] != 'EUR')
        euro_details = next(t for t in transactions if
                            t['Type'] == 'Algemeen valutaomrekening' and t['Valuta'] == 'EUR')
        foreign_details = next(t for t in transactions if
                               t['Type'] == 'Algemeen valutaomrekening' and t['Valuta'] != 'EUR')
        # Check the right transactions were found
        assert euro_details['Reference Txn ID'] == sale['Reference Txn ID'] or sale['Transactiereferentie']
        assert foreign_details['Reference Txn ID'] == sale['Reference Txn ID'] or sale['Transactiereferentie']

        rate = (euro_details['Bruto'] / -foreign_details['Net']).quantize(Decimal('.0000001'), rounding=ROUND_HALF_UP)

        exact_transaction = self.make_transaction(sale, rate)

        # Check if an extra line is necessary to handle any left-over foreign species
        # This happens (very rarly), probably due to bugs at PayPal.
        diff = sale['Net'] + foreign_details['Bruto']
        diff_euros = (diff * rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if diff:
            comment = 'Restant in vreemde valuta, ref: %s'%foreign_details['Transactiereferentie']
            foreign_valuta = sale['Valuta']
            lines = [(self.config.pp_kruispost, GLAccountTypes.General,
                         comment,
                      diff_euros, diff, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account),
                     (self.config.pp_account, GLAccountTypes.Bank,
                      comment,
                      -diff_euros, -diff, foreign_valuta, rate,
                      '')
                     ]
            exact_transaction.lines.extend([ExactTransactionLine(*l) for l in lines])
            logging.debug('Paypal left some foreign species on the account, %s'%diff)

        return exact_transaction

    def detailsGenerator(self, fname):
        conversions_stack = {}  # Used to find the three transactions related to a valuta conversion
        try:
            # Download the PayPal Transactions
            reader = pp_reader(fname)
            # For each transaction, extract the accounting details
            for transaction in reader:
                # Skip memo transactions.
                if transaction['Effect op saldo'].lower() == 'memo':
                    continue
                if transaction['Type'] == 'Algemeen valutaomrekening' or transaction['Valuta'] != 'EUR':
                    # We need to compress the next three transactions into a single, foreign valuta one.
                    ref = transaction['Reference Txn ID'] or transaction['Transactiereferentie']
                    txs = conversions_stack.setdefault(ref, [])
                    txs.append(transaction)
                    if len(txs) == 3:
                        yield self.make_foreign_transaction(txs)
                        del conversions_stack[ref]
                else:
                    yield self.make_transaction(transaction)
        except StopIteration:
            return
        except Exception as e:
            traceback.print_exc()

    def run(self):
        # The actual worker
        fname = downloadTransactions(*self.pp_login)
        xml_lines = [generateExactTransaction(details) for details in self.detailsGenerator(fname)]

        # Upload the XML to Exact


class Worker:
    keyring = None
    tasks = {}
    exact_token = None
    oauth = None

    @property
    def sockname(self):
        return os.path.join(config.opsdir, appconfig.readersock)

    @property
    def keyringname(self):
        return os.path.join(config.opsdir, appconfig.keyring)

    @expose
    def unlock(self, password):
        self.keyring = KeyRing(self.keyringname, password)

        # Now we can access the client secret for OAuth login
        client_id = '49b30776-9a29-4a53-b69d-a578712e997a'
        client_secret = self.keyring[client_id]
        if client_secret:
            self.oauth = OAuth2('https://start.exactonline.nl/api/oauth2/token',
                                client_id,
                                client_secret,
                                'http://paypal_reader.overzichten.nl:13959/oauth_code')
        else:
            logging.error('The client secret has not been set!')

    @expose
    def status(self):
        return dict(keyring='unlocked' if self.keyring else 'locked',
                    tasks=[t.name for t in self.tasks],
                    exact_online='authenticated' if self.exact_token else 'locked')

    @expose
    def addtask(self, details: taskdetails):
        details = taskdetails(**details)
        self.tasks[details.name] = details
        self.keyring[details.name] = details

    @expose
    def setauthorizationcode(self, code):
        """ The authorization is used to get the access token """
        if self.exact_token:
            raise RuntimeError('The system is already authorized')
        token = self.oauth.getAccessToken(code)
        self.exact_token = token

        # Set a timer to refresh the token
        loop = asyncio.get_event_loop()
        loop.call_later(int(token['expires_in']) - 550, self.refreshtoken)

    def refreshtoken(self):
        """ Refresh the current access token """
        token = self.oauth.getAccessToken()
        self.exact_token = token

        # Set a timer to refresh the token again
        loop = asyncio.get_event_loop()
        loop.call_later(int(token['expires_in']) - 550, self.refreshtoken)

    @staticmethod
    @logging.log_exceptions
    def run():
        # In test mode, we need to create our own event loop
        print('Starting worker')
        if config.testmode():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        server = mkUnixServer(Worker(), Worker.sockname)
        loop = asyncio.get_event_loop()
        loop.create_task(server)
        loop.run_forever()


if __name__ == '__main__':
    print('Worker starting')
    Worker.run()
