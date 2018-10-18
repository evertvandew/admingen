

from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP
from dataclasses import dataclass, asdict
import re
import datetime
from typing import List, Tuple
import logging
import traceback
from admingen.db_api import the_db, sessionScope, DbTable, select, Required, Set, openDb, orm
from admingen.international import SalesType, PP_EU_COUNTRY_CODES
from admingen.clients.paypal import (downloadTransactions, pp_reader, PPTransactionDetails,
                                     PaypalSecrets, DataRanges, period2dt)
from enum import IntEnum

illegal_xml_re = re.compile(
            u'[&\x00-\x08\x0b-\x1f\x7f-\x84\x86-\x9f\ud800-\udfff\ufdd0-\ufddf\ufffe-\uffff]')

@dataclass
class ExactTransactionLine:
    date: datetime.date
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
    ledger: int
    lines: List[ExactTransactionLine]
    closingbalance: Decimal

@dataclass
class paypal_export_config:
    taskid:int
    customerid:int
    administration_hid:int
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
    purchase_needs_invoice: bool
    creditors_kruispost: str
    unknown_creditor: str
    pp_kruispost: str
    vat_account: str
    currency: str

    def __post_init__(self):
        self.sale_accounts = {SalesType.Local: self.sale_account_nl,
                              SalesType.EU_private: self.sale_account_eu_vat,
                              SalesType.EU_ICP: self.sale_account_eu_no_vat,
                              SalesType.Other: self.sale_account_world,
                              SalesType.Unknown: self.sale_account_nl}
        self.purchase_accounts = {SalesType.Local: self.purchase_account_nl,
                              SalesType.EU_private: self.purchase_account_eu_vat,
                              SalesType.EU_ICP: self.purchase_account_eu_no_vat,
                              SalesType.Other: self.purchase_account_world,
                              SalesType.Unknown: self.purchase_account_nl}
        self.vat_percentages = {SalesType.Local: Decimal('0.21'),
                                SalesType.EU_private: Decimal('0.21'),
                                SalesType.EU_ICP: Decimal('0.00'),
                                SalesType.Other: Decimal('0.00'),
                                SalesType.Unknown: Decimal('0.21')}
        self.classifier = None

    def classifyTransaction(self, transaction: PPTransactionDetails):
        """ Classify a transaction to determine account and VAT percentage """
        if self.classifier:
            t = self.classifier(transaction)
            # Check if the classifier could handle it.
            if t != SalesType.Unknown:
                return t

        # The classifier could not handle this transaction, classify it directly
        if self.purchase_needs_invoice and transaction.Net < 0:
            return SalesType.Invoiced
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

        # The transaction needs an invoice
        if region == SalesType.Invoiced:
            return self.creditors_kruispost, Decimal('0.00')

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
            #with sessionScope():
            #    txs = select(_ for _ in PaypalTransactionLog if _.ref == transaction.ReferenceTxnID)
            #    for tx in txs:
            #        return tx.exact_transaction.account, tx.exact_transaction.vat_percent
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
        if transaction.Valuta != self.currency:
            parts.append(str(transaction.Valuta))
            parts.append(str(transaction.Bruto))
        parts += ['Fact: %s'%transaction.Factuurnummer,
                  transaction.Note[:20],
                  'ref:%s' % transaction.Transactiereferentie
                 ]
        dirty = ' '.join(parts)

        clean = illegal_xml_re.sub('', dirty)
        return clean



# Create a cache for storing the details of earlier transactions
@DbTable
class PaypalTransactionLog:
    ref: Required(str, index=True)
    xref: str
    timestamp: datetime.datetime
    exact_transaction: Required('ExchangeTransactionLog')

@DbTable
class ExchangeTransactionLog:
    pp_transactions : Set(PaypalTransactionLog)
    amount: Decimal
    vat_percent : Decimal
    account: int
    batch: Required('PaypalExchangeBatch')

# Keep track of when transactions were last retrieved from PayPal
@DbTable
class PaypalExchangeBatch:
    task_id: int
    timestamp: datetime.datetime
    period_start: datetime.date
    period_end: datetime.date
    starting_balance: Decimal
    closing_balance: Decimal
    fatals: int
    errors: int
    warnings: int
    success: int
    transactions: Set(ExchangeTransactionLog)


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
            </GLTransactionLine>'''

ForeignLineTemplate = '''            <GLTransactionLine type="40" line="{linenr}" status="20">
                <Date>{date}</Date>
                <FinYear number="{year}" />
                <FinPeriod number="{period}" />
                <GLAccount code="{GLAccount}" type="{GLType}" />
                {additional}
                <Description>{Description}</Description>
                <ForeignAmount>
                    <Currency code="{Currency}" />
                    <Value>{Amount}</Value>
                    <Rate>{ConversionRate}</Rate>
                </ForeignAmount>
            </GLTransactionLine>'''

ForeignLineTemplateWithAmount = '''            <GLTransactionLine type="40" line="{linenr}" status="20">
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
                    <Rate>{ConversionRate}</Rate>
                </ForeignAmount>
            </GLTransactionLine>'''



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

# In PayPal, the order_nr has a strange string prepended ('papa xxxx')
# Define an RE to strip it.
order_nr_re = re.compile(r'\D+(\d+)')


class PaypalExactConverter:
    def __init__(self, config:paypal_export_config):
        self.config = config
        self.classifier = None


    def generateExactLine(self, transaction: ExactTransaction, line: ExactTransactionLine, linenr):
        index = transaction.lines.index(line)
        nr_lines = len(transaction.lines)
        year = line.date.strftime('%Y')
        period = line.date.strftime('%m')
        if line.ForeignCurrency != self.config.currency or line.Currency != 'EUR':
            return ForeignLineTemplate.format(**locals(), **asdict(line))
        return LineTemplate.format(**locals(), **asdict(line))

    def generateExactTransaction(self, transaction: ExactTransaction):
        transactionlines = '\n'.join([self.generateExactLine(transaction, line, int((count + 2) / 2)) \
                                      for count, line in enumerate(transaction.lines)])
        return TransactionTemplate.format(**locals(), **asdict(transaction))

    def generateExactTransactionsFile(self, transactions: List[ExactTransaction]):
        transactions_xml = [self.generateExactTransaction(t) for t in transactions]
        return FileTemplate.format(transactions='\n'.join(transactions_xml))

    def make_transaction(self, transaction: PPTransactionDetails, rate=1, batch=None) -> ExactTransaction:
        """ Translate a PayPal transaction into a set of Exact bookings
            :param rate: euro_amount / foreign_amount

            The amounts are rounded such that VAT payable benefits
        """
        # A regular payment in euro's
        gb_sales, vat_percentage = self.config.determineAccountVat(transaction)
        base_comment = self.config.determineComment(transaction)
        transactiondate = transaction.Datum.date()

        # Use the following sequence:
        # First booking: the VAT return on the transaction fee (if any)
        # Second booking: the transaction fee (without VAT)
        # Third booking: the actual sale
        # Fourth booking: the VAT on the sale

        foreign_valuta = transaction.Valuta

        # Cache the results
        exact_log = None
        if batch is not None:
            exact_log = ExchangeTransactionLog(batch=batch,
                                       vat_percent=vat_percentage,
                                       account=gb_sales,
                                       amount=transaction.Bruto)

            _ = PaypalTransactionLog(ref=transaction.Transactiereferentie,
                                     xref=transaction.ReferenceTxnID,
                                     timestamp=transaction.Datum,
                                     exact_transaction = exact_log)

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
                lines.append((transactiondate, self.config.vat_account, GLAccountTypes.General,
                             comment,
                             -vat_costs_euro, self.config.currency, -vat_costs, foreign_valuta, rate,
                             '<GLOffset code="%s" />'%self.config.pp_account))
                lines.append((transactiondate, self.config.pp_account, GLAccountTypes.Bank,
                              comment,
                              vat_costs_euro, self.config.currency, vat_costs, foreign_valuta, rate,
                              ''))
            # The actual fee
            comment = 'Kosten ' + base_comment
            lines.append((transactiondate, self.config.costs_account, GLAccountTypes.SalesMarketingGeneralExpenses,
                         comment,
                          -net_costs_euro, self.config.currency, -net_costs, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account))
            lines.append((transactiondate, self.config.pp_account, GLAccountTypes.Bank,
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
        additional = '<GLOffset code="%s" />'%self.config.pp_account
        if gb_sales == self.config.creditors_kruispost:
            additional += '<Account code="%s" />'%self.config.unknown_creditor
            account_type = GLAccountTypes.AccountsPayable
        else:
            account_type = GLAccountTypes.Revenue
        lines.append((transactiondate, gb_sales, account_type,
                         comment,
                      -net_euro, self.config.currency, -net, foreign_valuta, rate,
                         additional))
        lines.append((transactiondate, self.config.pp_account, GLAccountTypes.Bank,
                         comment,
                      net_euro, self.config.currency, net, foreign_valuta, rate,
                         ''))

        # The VAT over the sale
        if vat_euro != Decimal('0.00'):
            comment = 'BTW ' + base_comment
            lines.append((transactiondate, self.config.vat_account, GLAccountTypes.General,
                          comment,
                          -vat_euro, self.config.currency, -vat, foreign_valuta, rate,
                             '<GLOffset code="%s" />'%self.config.pp_account))
            lines.append((transactiondate, self.config.pp_account, GLAccountTypes.Bank,
                          comment,
                          vat_euro, self.config.currency, vat, foreign_valuta, rate,
                             ''))

        lines = [ExactTransactionLine(*l) for l in lines]

        return lines, transaction.Saldo

        exact_transaction = ExactTransaction(transaction.Datum, self.config.ledger, lines,
                                       transaction.Saldo)
        return exact_transaction, exact_log

    def make_foreign_transaction(self, transactions: List[PPTransactionDetails], batch):
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

        lines, saldo = self.make_transaction(sale, rate, batch=batch)

        transactiondate = lines[0].date


        #for tx in [valuta_details, foreign_details]:
        #    _ = PaypalTransactionLog(ref=tx.Transactiereferentie,
        #                             xref=tx.ReferenceTxnID,
        #                             timestamp=tx.Datum,
        #                             exact_transaction=log)

        # Check if an extra line is necessary to handle any left-over foreign species
        # This happens (very rarly), probably due to bugs at PayPal.
        diff = sale.Net + foreign_details.Bruto
        diff_euros = (diff * rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if diff:
            comment = 'Restant in vreemde valuta, ref: %s'%foreign_details.Transactiereferentie
            foreign_valuta = sale.Valuta
            extra = [(transactiondate, self.config.pp_kruispost, GLAccountTypes.General,
                         comment,
                      diff_euros, self.config.currency, diff, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account),
                     (transactiondate, self.config.pp_account, GLAccountTypes.Bank,
                      comment,
                      -diff_euros, self.config.currency, -diff, foreign_valuta, rate,
                      '')
                     ]
            lines.extend([ExactTransactionLine(*l) for l in extra])
            logging.debug('Paypal left some foreign species on the account, %s'%diff)

        return lines, valuta_details.Saldo

        exact_transaction.closingbalance = valuta_details.Saldo
        return exact_transaction


    def groupedDetailsGenerator(self, fname, batch):
        conversions_stack = {}  # Used to find the three transactions related to a valuta conversion
        lines = []
        current_period = None
        try:
            # Download the PayPal Transactions
            reader: List[PPTransactionDetails] = pp_reader(fname)
            # For each transaction, extract the accounting details
            for transaction in reader:
                period = (transaction.Datum.year, transaction.Datum.month)
                current_period = current_period or period
                if period != current_period and lines:
                    yield ExactTransaction(self.config.ledger, lines, saldo)
                    lines = []
                    current_period = period
                # Skip memo transactions.
                if transaction.Effectopsaldo.lower() == 'memo':
                    continue
                if transaction.Type == 'Algemeen valutaomrekening' or \
                   transaction.Valuta != self.config.currency:
                    # We need to compress the next three transactions into a single, foreign valuta one.
                    # The actual transaction is NOT a conversion and is in foreign valuta.
                    # The two conversions refer to this transaction
                    if transaction.Type.strip() not in ['Algemeen valutaomrekening', 'Terugbetaling', 'Bank Deposit to PP Account']:
                        ref = transaction.Transactiereferentie
                    else:
                        ref = transaction.ReferenceTxnID
                    txs = conversions_stack.setdefault(ref, [])
                    txs.append(transaction)
                    if len(txs) == 3:
                        new_lines, saldo = self.make_foreign_transaction(txs, batch)
                        lines.extend(new_lines)
                        del conversions_stack[ref]
                else:
                    new_lines, saldo = self.make_transaction(transaction, batch=batch)
                    lines.extend(new_lines)

            if lines:
                yield ExactTransaction(self.config.ledger, lines, saldo)
        except:
            traceback.print_exc()

    def detailsGenerator(self, fname, batch):
        """ Generator that reads a list of PayPal transactions, and yields ExactTransactions """
        conversions_stack = {}  # Used to find the three transactions related to a valuta conversion
        try:
            # Download the PayPal Transactions
            reader: List[PPTransactionDetails] = pp_reader(fname)
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
                    if transaction.Type.strip() not in ['Algemeen valutaomrekening', 'Terugbetaling', 'Bank Deposit to PP Account']:
                        ref = transaction.Transactiereferentie
                    else:
                        ref = transaction.ReferenceTxnID
                    txs = conversions_stack.setdefault(ref, [])
                    txs.append(transaction)
                    if len(txs) == 3:
                        lines, saldo = self.make_foreign_transaction(txs, batch)
                        yield ExactTransaction(self.config.ledger, lines, saldo)
                        del conversions_stack[ref]
                else:
                    lines, saldo = self.make_transaction(transaction, batch=batch)
                    yield ExactTransaction(self.config.ledger, lines, saldo)

        except StopIteration:
            return
        except Exception as e:
            #traceback.print_exc()
            raise


    def convertTransactions(self, pp_fname, batch) -> Tuple[List[ExactTransaction], str]:
        """ Convert a paypal transaction """
        transactions: List[ExactTransaction] = list(self.groupedDetailsGenerator(pp_fname, batch))

        # If there are no transactions, quit
        if len(transactions) == 0:
            return

        xml = self.generateExactTransactionsFile(transactions)

        return transactions, xml



if __name__ == '__main__':
    from admingen.data import DataReader

    data = DataReader('taskconfig.csv')
    config = data['TaskConfig'][0]
    config = paypal_export_config(**config.__dict__)
    converter = PaypalExactConverter(config)
    testfname = '/home/ehwaal/tmp/pp_export/test-data/twease/Download.CSV'
    transactions = converter.groupedDetailsGenerator(testfname, None)
    xml = converter.generateExactTransactionsFile(transactions)
    fname = 'test_transactions.xml'
    with open(fname, 'w') as of:
        of.write(xml)

