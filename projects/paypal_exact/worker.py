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
import sys
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP
import traceback
from enum import IntEnum
from typing import List, Tuple, Dict, Any
import re
import threading

from admingen.servers import mkUnixServer, Message, expose, serialize, deserialize, update
from admingen import config
from admingen.logging import log_exceptions
from admingen.clients.paypal import (downloadTransactions, pp_reader, PPTransactionDetails,
                                     PaypalSecrets, DataRanges)
from admingen.clients import zeke
from admingen import logging
from admingen.db_api import the_db, sessionScope, DbTable, select, Required, Set, openDb, orm
from admingen.international import SalesType, PP_EU_COUNTRY_CODES
from admingen.dataclasses import dataclass, fields, asdict
from admingen.worker import Worker


@Message
class paypallogin:
    administration: int
    paypal_client_id: str
    client_password: str
    client_cert: bytes


@Message
class ExactSecrets:
    administration: int
    client_id: str
    client_secret: str
    client_token: str

@dataclass
class ExactTransactionLine:
    GLAccount: int
    GLType: int
    Description: str
    Amount: Decimal
    Currency: str
    ForeignAmount: Decimal
    ForeignCurrency: str
    ConversionRate: Decimal
    additional: str

@dataclass
class ExactTransaction:
    date: datetime
    ledger: int
    lines: List[ExactTransactionLine]
    closingbalance: Decimal

@dataclass
class paypal_export_config:
    ledger: str
    costs_account: str
    pp_account: str
    sale_account_nl: str
    sale_account_eu_vat: str
    sale_account_eu_no_vat: str
    sale_account_world: str
    purchase_account_nl: str
    purchase_account_eu_vat: str
    purchase_account_eu_no_vat: str
    purchase_account_world: str
    pp_kruispost: str
    vat_account: str
    currency: str


# Create a cache for storing the details of earlier transactions
@DbTable
class TransactionLog:
    timestamp : datetime.datetime
    pp_tx : str
    vat_percent : Decimal
    pp_username : Required(str, index=True)
    account: int

# Keep track of when transactions were last retrieved from PayPal
@DbTable
class PaypalExchangeLog:
    task_id: int
    timestamp: datetime.datetime


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
                    <Currency code="{Currency}" />
                    <Value>{Amount}</Value>
                </Amount>
                <ForeignAmount>
                    <Currency code="{Currency}" />
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
    return LineTemplate.format(**locals(), **asdict(line))


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
    return TransactionTemplate.format(**locals(), **asdict(transaction))


def generateExactTransactionsFile(transactions: List[ExactTransaction]):
    transactions_xml = [generateExactTransaction(t) for t in transactions]
    return FileTemplate.format(transactions = '\n'.join(transactions_xml))


# In PayPal, the order_nr has a strange string prepended ('papa xxxx')
# Define an RE to strip it.
order_nr_re = re.compile(r'\D+(\d+)')

def zeke_classifier(transaction: PPTransactionDetails):
    """ Let the Zeke client classify a PayPal transaction """
    match = order_nr_re.match(transaction.Factuurnummer)
    if match:
        order_nr = match.groups()[0]
        return zeke.classifySale(order_nr)
    return SalesType.Unknown


class PaypalExactTask:
    """ Produce exact transactions based on the PayPal transactions """
    config: [paypal_export_config]
    optional_config: [zeke.ZekeDetails]
    secrets: [ExactSecrets, PaypalSecrets]
    optional_secrets: [zeke.ZekeSecrets]

    def __init__(self, task_id, config_details, secrets):
        self.task_id = task_id
        self.exact_token, self.pp_login = secrets[:2]
        # TODO: Handle the optional secrets
        self.config = config_details if isinstance(config_details, paypal_export_config) \
            else config_details[0]

        self.classifier = None
        if isinstance(config_details, list) and len(config_details) > 1:
            for option in config_details[1:]:
                if isinstance(option, zeke.ZekeDetails):
                    self.classifier = zeke.classifySale

        # TODO: Handle the optional configuration
        self.sale_accounts = {SalesType.Local: self.config.sale_account_nl,
                              SalesType.EU_private: self.config.sale_account_eu_vat,
                              SalesType.EU_ICP: self.config.sale_account_eu_no_vat,
                              SalesType.Other: self.config.sale_account_world,
                              SalesType.Unknown: self.config.sale_account_nl}
        self.purchase_accounts = {SalesType.Local: self.config.purchase_account_nl,
                              SalesType.EU_private: self.config.purchase_account_eu_vat,
                              SalesType.EU_ICP: self.config.purchase_account_eu_no_vat,
                              SalesType.Other: self.config.purchase_account_world,
                              SalesType.Unknown: self.config.purchase_account_nl}
        self.vat_percentages = {SalesType.Local: Decimal('0.21'),
                                SalesType.EU_private: Decimal('0.21'),
                                SalesType.EU_ICP: Decimal('0.00'),
                                SalesType.Other: Decimal('0.00'),
                                SalesType.Unknown: Decimal('0.21')}

        self.pp_username = self.pp_login.username

        with sessionScope():
            q = select(t.timestamp for t in PaypalExchangeLog if t.task_id==task_id).order_by(lambda: orm.desc(t.timestamp))
            self.last_run = q.first()

        # Ensure the download directory exists
        if not os.path.exists(config.downloaddir):
            os.mkdir(config.downloaddir)


    def classifyTransaction(self, transaction: PPTransactionDetails):
        """ Classify a transaction to determine account and VAT percentage """
        if self.classifier:
            t = self.classifier(transaction)
            # Check if the classifier could handle it.
            if t != SalesType.Unknown:
                return t

        # The classifier could not handle this transaction, classify it directly
        if transaction.Landcode == 'NL':
            return SalesType.Local
        elif transaction.Landcode in PP_EU_COUNTRY_CODES:
            # EU is complex due to the ICP rules.
            return SalesType.Unknown
        elif transaction.Landcode:
            return SalesType.Other
        else:
            return SalesType.Unknown


    def determineAccountVat(self, transaction: PPTransactionDetails):
        """ Determine the grootboeken to be used for a specific transaction """

        if transaction.Type == 'Algemene opname' or 'withdrawl' in transaction.Type:
            # A bank withdrawl goes directly to the kruispost
            return self.config.pp_kruispost, Decimal('0.00')

        # Determine if the transaction is within the Netherlands, the EU or the world.
        region = self.classifyTransaction(transaction)
        accounts = self.sale_accounts if transaction.Net > 0 else self.purchase_accounts

        if region == SalesType.Unknown:
            if transaction.Valuta != 'EUR':
                # non-euro transactions are assumed to be outside the EU
                return accounts[SalesType.Other], self.vat_percentages[SalesType.Other]
            if transaction.Net > 0:
                # Sales with an unknown region are parked on the kruispost
                return self.config.pp_kruispost, Decimal('0.00')

        if transaction.ReferenceTxnID:
            # This is related to another payment, in almost all cases a return of a previous payment
            # If available, use the details from the previous transaction
            with sessionScope():
                txs = select(_ for _ in TransactionLog if _.pp_tx == transaction.ReferenceTxnID)
                for tx in txs:
                    return tx.account, tx.vat_percent
            # Transaction unknown, try to guess the details
            # This means that debtors and creditors are reversed
            accounts = self.sale_accounts if transaction.Net < 0 else self.purchase_accounts

        return accounts[region], self.vat_percentages[region]


    def determineComment(self, transaction: PPTransactionDetails):
        """ Determine the comment for a specific transaction """
        # For purchases, insert the email address
        parts = []
        if transaction.Bruto < 0 and transaction.ReferenceTxnID == '':
            parts.append(transaction.Naaremailadres)
        if transaction.Valuta != 'EUR':
            parts.append(str(transaction.Valuta))
            parts.append(str(transaction.Bruto))
        parts += ['Fact: %s'%transaction.Factuurnummer,
                  transaction.Note,
                  'ref:%s' % transaction.Transactiereferentie
                 ]
        return ' '.join(parts)

    def make_transaction(self, transaction: PPTransactionDetails, rate=1) -> ExactTransaction:
        """ Translate a PayPal transaction into a set of Exact bookings
            :param rate: euro_amount / foreign_amount

            The amounts are rounded such that VAT payable benefits
        """
        # A regular payment in euro's
        gb_sales, vat_percentage = self.determineAccountVat(transaction)
        base_comment = self.determineComment(transaction)

        # Use the following sequence:
        # First booking: the VAT return on the transaction fee (if any)
        # Second booking: the transaction fee (without VAT)
        # Third booking: the actual sale
        # Fourth booking: the VAT on the sale

        foreign_valuta = transaction.Valuta

        # Cache the results
        with sessionScope():
            c = TransactionLog(timestamp=transaction.Datum,
                               pp_tx=transaction.ReferenceTxnID,
                               vat_percent=vat_percentage,
                               pp_username=self.pp_username,
                               account=gb_sales)

        lines = []
        net_costs_euro = vat_costs_euro = Decimal('0.00')
        if transaction.Fee:
            # If the payment includes VAT, the VAT on the fee can be deducted
            # The gross amount equals 1.21 times the net amount, so dividing should get the net.
            net_costs = (transaction.Fee / (Decimal(1.00)+vat_percentage)).quantize(Decimal('.01'), rounding=ROUND_UP)
            vat_costs = transaction.Fee - net_costs
            net_costs_euro  = (net_costs*rate).quantize(Decimal('.01'), rounding=ROUND_UP)
            vat_costs_euro = (vat_costs*rate).quantize(Decimal('.01'), rounding=ROUND_DOWN)
            if vat_costs_euro != Decimal(0.00):
                # The VAT over the fee
                comment = 'BTW kosten ' + base_comment
                lines.append((self.config.vat_account, GLAccountTypes.General,
                             comment,
                             -vat_costs_euro, self.config.currency, -vat_costs, foreign_valuta, rate,
                             '<GLOffset code="%s" />'%self.config.pp_account))
                lines.append((self.config.pp_account, GLAccountTypes.Bank,
                              comment,
                              vat_costs_euro, self.config.currency, vat_costs, foreign_valuta, rate,
                              ''))
            # The actual fee
            comment = 'Kosten ' + base_comment
            lines.append((self.config.costs_account, GLAccountTypes.SalesMarketingGeneralExpenses,
                         comment,
                          -net_costs_euro, self.config.currency, -net_costs, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account))
            lines.append((self.config.pp_account, GLAccountTypes.Bank,
                          comment,
                          net_costs_euro, self.config.currency, net_costs, foreign_valuta, rate,
                          ''))

        # Here, the difference between Net and Gross is the taxes to be deducted.
        # The actual sale. The net figure still includes the fee, only the sales tax is deducted,
        # as the sales price to the customer always includes all costs incurred for that sale.
        # These calculations must be exact as they must reflect the bank saldo in Paypal.
        net = (transaction.Bruto / (Decimal(1.00) + vat_percentage)).quantize(Decimal('.01'),
                                                                            rounding=ROUND_DOWN)
        vat = transaction.Bruto - net

        if rate != Decimal('1.00'):
            # The rate was determine by dividing the net amounts of foreign money and the gross local valuta
            # Thus this calculation should be exact to the resolution of rate (0.0000001)
            # PayPal net amounts have the transaction costs deducted, not the taxes.
            # Thus to get the real gross in local currency, the costs must be added.
            ppnet_euro = (transaction.Net * rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            gross_euro = ppnet_euro - net_costs_euro - vat_costs_euro
        else:
            gross_euro = transaction.Bruto
        # Our definition of 'Net' is the amount after taxes
        net_euro = (gross_euro / (Decimal(1.00) + vat_percentage)).quantize(Decimal('.01'),
                                                                            rounding=ROUND_DOWN)
        vat_euro = gross_euro - net_euro
        comment = base_comment
        lines.append((gb_sales, GLAccountTypes.Revenue,
                         comment,
                      -net_euro, self.config.currency, -net, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account))
        lines.append((self.config.pp_account, GLAccountTypes.Bank,
                         comment,
                      net_euro, self.config.currency, net, foreign_valuta, rate,
                         ''))

        # The VAT over the sale
        if vat_euro != Decimal('0.00'):
            comment = 'BTW ' + base_comment
            lines.append((self.config.vat_account, GLAccountTypes.General,
                          comment,
                          -vat_euro, self.config.currency, -vat, foreign_valuta, rate,
                             '<GLOffset code="%s" />'%self.config.pp_account))
            lines.append((self.config.pp_account, GLAccountTypes.Bank,
                          comment,
                          vat_euro, self.config.currency, vat, foreign_valuta, rate,
                             ''))

        lines = [ExactTransactionLine(*l) for l in lines]

        exact_transaction = ExactTransaction(transaction.Datum, self.config.ledger, lines,
                                       transaction.Saldo)
        return exact_transaction

    def make_foreign_transaction(self, transactions: List[PPTransactionDetails]):
        # Get the details from the original transaction
        sale:PPTransactionDetails = next(t for t in transactions if
                    t.Type != 'Algemeen valutaomrekening' and t.Valuta != self.config.currency)
        valuta_details:PPTransactionDetails = next(t for t in transactions if
                            t.Type == 'Algemeen valutaomrekening' and t.Valuta == self.config.currency)
        foreign_details:PPTransactionDetails = next(t for t in transactions if
                               t.Type == 'Algemeen valutaomrekening' and t.Valuta != self.config.currency)
        # Check the right transactions were found
        assert valuta_details.ReferenceTxnID == sale.ReferenceTxnID or sale.Transactiereferentie
        assert foreign_details.ReferenceTxnID == sale.ReferenceTxnID or sale.Transactiereferentie

        # Paypal converts the net amount of foreign money into the gross amount of local money
        rate = (valuta_details.Bruto / -foreign_details.Net).quantize(Decimal('.0000001'), rounding=ROUND_HALF_UP)

        exact_transaction = self.make_transaction(sale, rate)
        exact_transaction.closingbalance = valuta_details.Saldo

        # Check if an extra line is necessary to handle any left-over foreign species
        # This happens (very rarly), probably due to bugs at PayPal.
        diff = sale.Net + foreign_details.Bruto
        diff_euros = (diff * rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if diff:
            comment = 'Restant in vreemde valuta, ref: %s'%foreign_details.Transactiereferentie
            foreign_valuta = sale.Valuta
            lines = [(self.config.pp_kruispost, GLAccountTypes.General,
                         comment,
                      diff_euros, self.config.currency, diff, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account),
                     (self.config.pp_account, GLAccountTypes.Bank,
                      comment,
                      -diff_euros, self.config.currency, -diff, foreign_valuta, rate,
                      '')
                     ]
            exact_transaction.lines.extend([ExactTransactionLine(*l) for l in lines])
            logging.debug('Paypal left some foreign species on the account, %s'%diff)

        return exact_transaction

    def detailsGenerator(self, fname):
        """ Generator that reads a list of PayPal transactions, and yields ExactTransactions """
        conversions_stack = {}  # Used to find the three transactions related to a valuta conversion
        try:
            # Download the PayPal Transactions
            reader: List(PPTransactionDetails) = pp_reader(fname)
            # For each transaction, extract the accounting details
            for transaction in reader:
                # Skip memo transactions.
                if transaction.Effectopsaldo.lower() == 'memo':
                    continue
                if transaction.Type == 'Algemeen valutaomrekening' or \
                   transaction.Valuta != self.config.currency:
                    # We need to compress the next three transactions into a single, foreign valuta one.
                    # The actual transaction is NOT a conversion and is in foreign valuta.
                    # The two conversions refer to this transaction
                    if transaction.Type != 'Algemeen valutaomrekening':
                        ref = transaction.Transactiereferentie
                    else:
                        ref = transaction.ReferenceTxnID
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
            #traceback.print_exc()
            raise

    @log_exceptions
    def run(self, period: DataRanges=DataRanges.Yesterday):
        """ The actual worker. Loads the transactions for yesterday and processes them """
        print ('RUNNING')

        # Load the transaction from PayPal
        fname = '/home/ehwaal/admingen/downloads/Download (1).CSV'
        #fname = downloadTransactions(self.pp_login, period)
        #zeke_details = zeke.loadTransactions()
        transactions: List[ExactTransaction] = list(self.detailsGenerator(fname))
        xml = generateExactTransactionsFile(transactions)
        fname = 'exact_transactions.xml'
        with open(fname, 'w') as of:
            of.write(xml)

        total = sum(sum(l.Amount for l in t.lines if l.GLAccount==self.config.pp_account)
                    for t in transactions)
        logging.info('Written exact transactions to %s: %s\t%s'%(fname, len(transactions), total))

        # Upload the XML to Exact

        # Log the exchange
        with sessionScope():
            _ = PaypalExchangeLog(task_id=self.task_id, timestamp=datetime.datetime.now())


if __name__ == '__main__':
    config.load_context()
    worker = Worker(PaypalExactTask)
    print('Worker starting')
    worker.run(DataRanges.Past3Months)
