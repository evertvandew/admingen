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

import paypalrestsdk
from paypalrestsdk.payments import Payment
from admingen.servers import mkUnixServer, Message, expose
from admingen.keyring import KeyRing
from admingen.email import sendmail
from admingen import config
from admingen.clients.rest import OAuth2
from admingen.clients.paypal import downloadTransactions, pp_reader
from admingen import logging


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


mailconfig = dict(adminmail='evert.vandewaal@xs4all.nl',
                  selfmail='paypalchecker@ehud',
                  appname='Paypal Exporter',
                  keyring='appkeyring.enc')

bootmail = '''I have restarted, and need my keyring unlocked!

Your faithful servant, %s'''

if False:
    # First let the maintainer know we are WAITING!
    sendmail(config['adminmail'], config['selfmail'],
             'Waiting for action',
             bootmail % config['appname'])

ExactTransaction = namedtuple('ExactTransaction', ['Date', 'ledger', 'lines', 'ClosingBalance'])
ExactTransactionLine = namedtuple('ExactTransactionLine',
                                  ['GLAccount', 'Description', 'Amount', 'ForeignAmount',
                                   'ForeignCurrency', 'ConversionRate'])
WorkerConfig = namedtuple('WorkerConfig',
                          ['ledger', 'costs_account', 'pp_account', 'debtors_account',
                           'creditors_account',
                           'pp_kruispost'])

LineTemplate = '''<GLTransactionLine type="40" linetype="0" line="{nr_lines}">
                <Date>{date}</Date>
                <FinYear number="{year}" />
                <FinPeriod number="{period}" />
                <GLAccount code="{GLAccount}" type="110">
                </GLAccount>
                <Description>{Description}</Description>
                <Amount>
                    <Currency code="EUR" />
                    <Value>{Amount}</Value>
                </Amount>
                <ForeignAmount>
					<Currency code="{ForeignCurrency}" />
					<Value>{ForeignAmount}</Value>
					<Rate>{ConversionRate}</Rate>
				</ForeignAmount>
            </GLTransactionLine>'''


def generateExactLine(transaction, line):
    index = transaction.lines.index(line)
    nr_lines = len(transaction.lines)
    date = transaction.Date.strftime('%Y-%m-%d')
    year = transaction.Date.strftime('%Y')
    period = transaction.Date.strftime('%m')
    return LineTemplate.format(**locals(), **line._asdict())


TransactionTemplate = '''        <GLTransaction>
            <TransactionType number="40">
                <Description>Cash flow</Description>
            </TransactionType>
            <Journal code="{ledger}" />
            {transactionlines}
            </GLTransaction>'''

FileTemplate = '''<?xml version="1.0" encoding="utf-8"?>
<eExact xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="eExact-XML.xsd">
	<GLTransactions>
{transactions}
	</GLTransactions>
	<Messages />
</eExact>
'''

def generateExactTransaction(transaction):
    transactionlines = '\n'.join([generateExactLine(transaction, line) \
                                  for line in transaction.lines])
    return TransactionTemplate.format(**locals(), **transaction._asdict())


def generateExactTransactionsFile(transactions):
    transactions = [generateExactTransaction(t) for t in transactions]
    return FileTemplate.format(transactions = '\n'.join(transactions))


class PaypalExactTask:
    """ Produce exact transactions based on the PayPal transactions """
    def __init__(self, pp_login, config: WorkerConfig, exact_token):
        self.pp_login, self.config, self.exact_token = pp_login, config, exact_token

    def determineAccounts(self, transaction):
        """ Determine the grootboeken to be used for a specific transaction """

        # The default for normal payments
        gb2 = self.config.debtors_account if transaction['Net'] > 0 else self.config.creditors_account

        if transaction['Reference Txn ID']:
            # This is related to another payment, in almost all cases a return of a previous payment
            # This means that debtors and creditors are reversed
            gb2 = self.config.debtors_account if transaction['Net'] < 0 else self.config.creditors_account

        if transaction['Type'] == 'Algemene opname':
            # A bank withdrawl goes to the kruispost
            gb2 = self.config.pp_kruispost

        return self.config.pp_account, gb2

    def determineComment(self, transaction):
        """ Determine the comment for a specific transaction """
        return 'ref:%s'%transaction['Transactiereferentie']

    def make_normal_transaction(self, transaction):
        # A regular payment in euro's
        gb1, gb2 = self.determineAccounts(transaction)
        comment = self.determineComment(transaction)
        lines = []
        rate = Decimal('1')
        lines.append(
            ExactTransactionLine(gb1, comment, transaction['Bruto'], transaction['Bruto'], 'EUR', rate))
        lines.append(ExactTransactionLine(gb2, comment, -transaction['Bruto'], -transaction['Bruto'], 'EUR', rate))
        # Check if a third and fourth line need to be added to account for the costs of the transaction
        if transaction['Fee']:
            lines.append(ExactTransactionLine(gb1, 'Kosten Paypal transactie',
                                              transaction['Fee'], transaction['Fee'], 'EUR', rate))
            lines.append(ExactTransactionLine(self.config.costs_account, 'Kosten Paypal transactie',
                                              -transaction['Fee'], -transaction['Fee'], 'EUR', rate))

        transaction = ExactTransaction(transaction['Datum'], self.config.ledger, lines,
                                       transaction['Saldo'])
        return transaction

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

        gb1, gb2 = self.determineAccounts(sale)
        comment = self.determineComment(sale)
        rate = (euro_details['Bruto'] / -foreign_details['Net']).quantize(Decimal('.0000001'), rounding=ROUND_HALF_UP)

        if sale['Fee']:
            fee = (sale['Fee'] * rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            euro_details['Bruto'] -= fee

        lines = []

        # Check if an extra line is necessary to handle any left-over foreign species
        # This happens (very rarly), probably due to bugs at PayPal.
        diff = sale['Net'] + foreign_details['Bruto']
        diff_euros = (diff * rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if diff:
            logging.debug('Paypal left some foreign species on the account, %s'%diff)
            comment = 'Restant in vreemde valuta, ref: %s'%foreign_details['Transactiereferentie']
            lines.append(ExactTransactionLine(self.config.pp_account,
                      comment,
                      -diff_euros, -diff,sale['Valuta'], rate))
            lines.append(ExactTransactionLine(self.config.pp_kruispost, comment, diff_euros, diff, sale['Valuta'], rate))
            euro_details['Bruto'] += diff_euros

        lines.append(
            ExactTransactionLine(gb1, comment, euro_details['Bruto'], sale['Bruto'],
                                 sale['Valuta'], rate))
        lines.append(ExactTransactionLine(gb2, comment, -euro_details['Bruto'],
                                          -sale['Bruto'], sale['Valuta'], rate))
        # Check if a third and fourth line need to be added to account for the costs of the transaction
        if sale['Fee']:
            lines.append(ExactTransactionLine(gb1, 'Kosten Paypal transactie',
                                              fee, sale['Fee'], sale['Valuta'], rate))
            lines.append(ExactTransactionLine(self.config.costs_account, 'Kosten Paypal transactie',
                                              -fee, -sale['Fee'], sale['Valuta'], rate))


        transaction = ExactTransaction(sale['Datum'], self.config.ledger, lines, euro_details['Saldo'])

        return transaction

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
                    yield self.make_normal_transaction(transaction)
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
    sockname = '/home/ehwaal/tmp/paypalreader.sock' if config.testmode() else \
        '/run/paypalreader/readersock'
    keyringname = '/home/ehwaal/tmp/paypalreader.encr'

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
