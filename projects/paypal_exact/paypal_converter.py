
from io import StringIO
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP
from dataclasses import dataclass, asdict
import re
import datetime
from typing import List, Tuple
import logging
import traceback
import sys
import os.path
import glob
import xml.etree.ElementTree as ET
from admingen import db_api
from admingen.international import SalesType, PP_EU_COUNTRY_CODES
from admingen.clients.paypal import (downloadTransactions, pp_reader, PPTransactionDetails,
                                     PaypalSecrets, DataRanges, period2dt)
from admingen.clients.exact_xml import processAccounts
from enum import Enum, IntEnum

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
    account: str
    note: str

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
    refunds: str
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
    vat_code_nl: int
    vat_code_eu: int
    vat_code_icp: int
    vat_code_world: int
    vat_code_unknown: int
    handle_vat: bool
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
        self.vat_codes = {SalesType.Local: self.vat_code_nl,
                              SalesType.EU_private: self.vat_code_eu,
                              SalesType.EU_ICP: self.vat_code_icp,
                              SalesType.Other: self.vat_code_world,
                              SalesType.Unknown: self.vat_code_unknown}
        self.classifier = None
        self.persist = None
        self.known_transactions = {}

    def getType(self, t: PPTransactionDetails):
        """ The following transaction types are used:
                c: Transaction involving buying something from a supplier.
                d: Transaction involving a sale to a customer
                b: Transaction with a bank
                u: Transaction is 'Unknown', and is booked at a kruispost.
        """
        if True:
            code = 'u'
            tt = t.TT

            if tt == TT.UNKNOWN:
                pass
            elif tt in [TT.Withdrawal, TT.CurrencyConversion, TT.BankDeposit,
                        TT.CreditCardWithdrawal, TT.CreditCardDeposit]:
                code = 'b'
            elif tt == TT.Refund and t.ReferenceTxnID in self.known_transactions:
                code = self.known_transactions[t.ReferenceTxnID]
            else:
                # Determine if we are dealing with a purchase or sale.
                dont_invert = tt in [TT.CancelHold, TT.PreApprovedPayment, TT.AuthorizationHoldReversal,
                                     TT.ChargeBackReversal, TT.ReleaseAfterReview]
                no_refund = tt in [TT.HoldForDispute, TT.AuthorizationHold, TT.HoldForReview]

                invert = t.ReferenceTxnID and not dont_invert

                if invert:
                    if t.Net < 0:
                        if self.refunds and not no_refund:
                            code = 'r'
                        else:
                            code = 'd'
                    else:
                        code = 'c'
                elif t.Net > 0:
                    code = 'd'
                else:
                    code = 'c'

            self.known_transactions[t.Transactiereferentie] = code
            return code

        else:
            tt = t.Type.lower()
            if tt in ['algemene opname', 'algemeen valutaomrekening'] or 'withdrawal' in tt:
                return 'b'
            # TODO: find the Dutch translation of 'preapproved etc.'
            elif t.ReferenceTxnID and t.Net < 0 and t.Type not in ['PreApproved Payment Bill User Payment']:
                if self.refunds:
                    print ('Found a refund!')
                    return 'r'      # Retour zending oid
                return 'd'          # Just book it on the sales account.
            elif not t.ReferenceTxnID and t.Net > 0:
                return 'd'
            else:
                return 'c'


    def getRegion(self, t: PPTransactionDetails):
        # The classifier could not handle this transaction, classify it directly
        if self.purchase_needs_invoice and t.debitcredit == 'c':
            return SalesType.Invoiced
        if t.Landcode == 'NL':
            return SalesType.Local
        elif t.Landcode in PP_EU_COUNTRY_CODES:
            # EU is complex due to the ICP rules.
            return SalesType.Unknown
        elif t.Landcode:
            return SalesType.Other
        else:
            return SalesType.Unknown

    def getGLAccount(self, t: PPTransactionDetails):
        if t.debitcredit == 'b':
            return self.pp_kruispost

        if t.debitcredit == 'r':
            return self.refunds

        # The transaction needs an invoice
        if t.vatregion == SalesType.Invoiced:
            return self.creditors_kruispost

        accounts = self.sale_accounts if t.debitcredit == 'd' else self.purchase_accounts

        if t.vatregion == SalesType.Unknown:
            if t.Valuta != 'EUR':
                # non-euro transactions are assumed to be outside the EU
                return accounts[SalesType.Other]
            if t.debitcredit == 'd':
                # Assume that we need to pay BTW
                return self.sale_account_eu_vat

        if t.ReferenceTxnID:
            # This is related to another payment, in almost all cases a return of a previous payment
            # If available, use the details from the previous transaction
            #with sessionScope():
            #    txs = select(_ for _ in PaypalTransactionLog if _.ref == transaction.ReferenceTxnID)
            #    for tx in txs:
            #        return tx.exact_transaction.account, tx.exact_transaction.vat_percent
            # Transaction unknown, try to guess the details
            # This means that debtors and creditors are reversed
            accounts = self.sale_accounts if t.Net < 0 else self.purchase_accounts

        return accounts[t.vatregion]
    def getGLAType(self, t):
        if t.glaccount == self.creditors_kruispost:
            return GLAccountTypes.AccountsPayable.value
        return GLAccountTypes.Revenue.value

    def getTemplate(self, t: PPTransactionDetails):
        if t.Valuta != 'EUR' or getattr(t, 'ForeignValuta', self.currency) != self.currency:
            return 'ForeignLineTemplate'
        return 'LineTemplate'

    def getNote(self, transaction: PPTransactionDetails):
        t = transaction
        parts = {'Naam': t.Naam,
                 'Factuur': t.Factuurnummer,
                 'Type': t.Type,
                 'Tijd': t.Tijd,
                 'Artikel': t.ArtikelNaam,
                 'Artikel nr': t.ArtikelNr,
                 'Transactie': t.Transactiereferentie,
                 'Kruisref': t.ReferenceTxnID,
                 'Bedrag': t.Bruto,
                 'Kosten': t.Fee,
                 'Valuta': t.Valuta,
                 'Aantekning': t.Note}
        parts['Crediteur'] = t.Naaremailadres
        parts['Debiteur'] = t.Vanemailadres

        if hasattr(transaction, 'VatAccount'):
            parts['BTW account'] = transaction.VatAccount

        note = ', '.join('%s: %s'%i for i in parts.items() if i[1])
        return illegal_xml_re.sub('', note)

    def getComment(self, transaction: PPTransactionDetails):
        """ Determine the comment for a specific transaction """
        # For purchases, insert the email address
        parts = [transaction.Naam,
                 'Fact: %s'%transaction.Factuurnummer
                 ]
        if hasattr(transaction, 'VatAccount'):
            parts['BTW account'] = transaction.VatAccount

        icp = getattr(transaction, 'icpaccountnr', '')
        if icp:
            parts.insert(0, 'ICP: %s' % icp)

        dirty = ' '.join(parts)
        clean = illegal_xml_re.sub('', dirty)
        return clean

    ###########################################################################
    ## OOOOLD...

    def loadVatDetails(self, s : str):
        vat_details = {}
        if s.startswith('<?xml'):
            # This is XML data
            root = ET.fromstring(s)
            # Each VAT code has the percentage and the GL accounts for paying and claiming
            # The other details are not used.
            for vat in root.findall('*/VAT'):
                details = {}
                details['percentage'] = Decimal(vat.find('Percentage').text)
                details['pay_gla'] = int(vat.find('GLToPay').attrib['code'])
                details['claim_gla'] = int(vat.find('GLToClaim').attrib['code'])
                code = details['code'] = int(vat.attrib['code'])
                vat_details[code] = details
        else:
            raise RuntimeError('Format not supported')

        for t, c in [(SalesType.Local, self.vat_code_nl),
                     (SalesType.EU_private, self.vat_code_eu),
                     (SalesType.EU_ICP, self.vat_code_icp),
                     (SalesType.Other, self.vat_code_world),
                     (SalesType.Unknown, self.vat_code_unknown)]:
            self.vat_details[t] = vat_details[c]


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

        if transaction.Type == 'algemene opname' or 'withdrawal' in transaction.Type.lower():
            # A bank withdrawl goes directly to the kruispost
            return self.pp_kruispost, Decimal('0.00')

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
                # Assume that we need to pay BTW
                return self.sale_account_eu_vat, Decimal('0.21')

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

        return accounts[region], self.vat_percentages[region], vatcode


    def determineComment(self, transaction: PPTransactionDetails, account):
        """ Determine the comment for a specific transaction """
        # For purchases, insert the email address
        parts = [transaction.Naam,
                 'Fact: %s'%transaction.Factuurnummer
                 ]
        if account == self.sale_account_eu_no_vat:
            parts.append('btw:%s'%self.classifier.getBtwAccount(transaction))
        dirty = ' '.join(parts)

        clean = illegal_xml_re.sub('', dirty)
        return clean

    def determineNote(self, transaction: PPTransactionDetails, account):
        t = transaction
        parts = {'Naam': t.Naam,
                 'Factuur': t.Factuurnummer,
                 'Type': t.Type,
                 'Tijd': t.Tijd,
                 'Artikel': t.ArtikelNaam,
                 'Artikel nr': t.ArtikelNr,
                 'Transactie': t.Transactiereferentie,
                 'Kruisref': t.ReferenceTxnID,
                 'Bedrag': t.Bruto,
                 'Kosten': t.Fee,
                 'Valuta': t.Valuta,
                 'Aantekning': t.Note}
        if account == self.creditors_kruispost:
            parts['Crediteur'] = t.Naaremailadres
        elif account in self.sale_accounts:
            parts['Debiteur'] = t.Vanemailadres

        if account == self.sale_account_eu_no_vat:
            parts['BTW account'] = self.classifier.getBtwAccount(transaction)

        note = ', '.join('%s: %s'%i for i in parts.items() if i[1])
        return illegal_xml_re.sub('', note)


class TransactionTypes(Enum):
    AccountCorrection = 'General Account Correction'
    AuthorizationHold = 'Account Hold for Open Authorization'
    AuthorizationHoldReversal = 'Reversal of General Account Hold'
    BankDeposit = 'Bank Deposit to PP Account'
    CancelHold = 'Cancellation of Hold for Dispute Resolution'
    ChargeBack = 'Chargeback'
    ChargeBackFee = 'Chargeback Fee'
    ChargeBackReversal = 'Chargeback Reversal'
    CreditCardDeposit = 'General Credit Card Deposit'
    CreditCardWithdrawal = 'General Credit Card Withdrawal'
    CurrencyConversion = 'General Currency Conversion'
    Donation = 'Donation Payment'
    eBayPayment = 'eBay Auction Payment'
    ExpressPayment = 'Express Checkout Payment'
    HoldForDispute = 'Hold on Balance for Dispute Investigation'
    HoldForReview = 'Payment Review Hold'
    MassPayment = 'Mass Pay Payment'
    MobilePayment = 'Mobile Payment'
    Refund = 'Payment Refund'
    Reversal = 'Payment Reversal'
    ReleaseAfterReview = 'Payment Review Release'
    Payment = 'General Payment'
    PostagePayment = 'Postage Payment'
    PreApprovedPayment = 'PreApproved Payment Bill User Payment'
    SubscriptionPayment = 'Subscription Payment'
    WebsitePayment = 'Website Payment'
    Withdrawal = 'General Withdrawal'
    UNKNOWN = ''


TT = TransactionTypes

known_types_dutch = {
    TT.CancelHold: 'Annulering van blokkering voor geschillenoplossing',
    TT.CreditCardDeposit: 'Algemene creditcardstorting',
    TT.CreditCardWithdrawal: 'Algemene creditcardopname',
    TT.CurrencyConversion: 'Algemeen valutaomrekening',
    TT.BankDeposit: 'Creditcardstorting ter aanvulling saldo verschuldigd bedrag',
    TT.eBayPayment: 'Betaling eBay-veiling',
    TT.ExpressPayment: 'Express Checkout betaling',
    TT.HoldForDispute: 'Geblokkeerd saldo wegens onderzoek naar geschil',
    TT.Payment: 'Algemene betaling',
    TT.PreApprovedPayment: 'Vooraf goedgekeurde betaling gebruiker betaalfactuur',
    TT.SubscriptionPayment: 'Abonnementsbetaling',
    TT.Refund: 'Terugbetaling',
    TT.Reversal: 'Terugboeking betaling',
    TT.WebsitePayment: 'Websitebetaling'
}

known_types_rev = {v.value.replace(' ', '').lower(): v for k, v in TT.__members__.items()}
known_types_dutch_rev = {v.replace(' ', '').lower(): k for k, v in known_types_dutch.items()}

def match_transaction_type(tt):
    """ Look for the TransactionType matching this text.
    """
    # Remove spaces and make lower-key
    tt_filt = tt.replace(' ', '').lower()
    if tt_filt in known_types_rev:
        return known_types_rev[tt_filt]
    if tt_filt in known_types_dutch_rev:
        return known_types_dutch_rev[tt_filt]
    return TT.UNKNOWN


def add_transactionTypes(transactions):
    """ Set the TT field in each transaction
    """
    for t in transactions:
        t.TT = match_transaction_type(t.Type)
        yield t


def filter_foreign_references(transactions):
    for t in transactions:
        # Find references outside PayPal and move them to the factuur number.
        if '-' in t.ReferenceTxnID:
            t.Factuurnummer += t.ReferenceTxnID
            t.ReferenceTxnID = ''
        yield t


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
                {vattype}
                <FinYear number="{year}" />
                <FinPeriod number="{period}" />
                <GLAccount code="{GLAccount}" type="{GLType}" />
                {additional}
                <Description>{Description}</Description>
                {account}
                <Amount>
                    <Currency code="{Currency}" />
                    <Value>{Amount}</Value>
                </Amount>
                <Note>
                    {note}
                </Note>
            </GLTransactionLine>
'''

ForeignLineTemplate = '''            <GLTransactionLine type="40" line="{linenr}" status="20">
                <Date>{date}</Date>
                {vattype}
                <FinYear number="{year}" />
                <FinPeriod number="{period}" />
                <GLAccount code="{GLAccount}" type="{GLType}" />
                {additional}
                <Description>{Description}</Description>
                {account}
                <ForeignAmount>
                    <Currency code="{Currency}" />
                    <Value>{Amount}</Value>
                    <Rate>{ConversionRate}</Rate>
                </ForeignAmount>
                <Note>
                    {note}
                </Note>
            </GLTransactionLine>
'''

ForeignLineTemplateWithAmount = '''            <GLTransactionLine type="40" line="{linenr}" status="20">
                <Date>{date}</Date>
                {vattype}
                <FinYear number="{year}" />
                <FinPeriod number="{period}" />
                <GLAccount code="{GLAccount}" type="{GLType}" />
                {additional}
                <Description>{Description}</Description>
                {account}
                <Amount>
                    <Currency code="{Currency}" />
                    <Value>{Amount}</Value>
                    {vatline}
                    {vatdetails}
                </Amount>
                <ForeignAmount>
                    <Currency code="{Currency}" />
                    <Value>{Amount}</Value>
                    <Rate>{ConversionRate}</Rate>
                    {vatforeigndetails}
                </ForeignAmount>
                <Note>
                    {note}
                </Note>
            </GLTransactionLine>
'''



TransactionStartTemplate = '''        <GLTransaction>
            <TransactionType number="40" />
            <Journal code="{ledger}" type="12" />
'''
TransactionEndTemplate = '''        </GLTransaction>
'''

FileStartTemplate = '''<?xml version="1.0" encoding="utf-8"?>
<eExact xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="eExact-XML.xsd">
    <GLTransactions>
'''

FileEndTemplate = '''
    </GLTransactions>
</eExact>
'''

# In PayPal, the order_nr has a strange string prepended ('papa xxxx')
# Define an RE to strip it.
order_nr_re = re.compile(r'\D+(\d+)')


class PaypalExactConverter:
    def __init__(self, config:paypal_export_config):
        self.config = config


    def generateExactLine(self, transaction: ExactTransaction, line: ExactTransactionLine, linenr):
        index = transaction.lines.index(line)
        nr_lines = len(transaction.lines)
        year = line.date.strftime('%Y')
        period = line.date.strftime('%m')
        if line.ForeignCurrency != self.config.currency or line.Currency != 'EUR':
            return ForeignLineTemplate.format(**locals(), **asdict(line))
        return LineTemplate.format(**locals(), **asdict(line))

    def generateExactTransaction(self, transaction: ExactTransaction, ostream):
        ostream.write(TransactionStartTemplate.format(**locals(), **asdict(transaction)))
        for count, line in enumerate(transaction.lines):
            ostream.write(self.generateExactLine(transaction, line, int((count + 2) / 2)))
        ostream.write(TransactionEndTemplate)

    def generateExactTransactionsFile(self, transactions: List[ExactTransaction], ostream):
        ostream.write(FileStartTemplate)
        for t in transactions:
            self.generateExactTransaction(t, ostream)
        ostream.write(FileEndTemplate)

    def make_transaction(self, transaction: PPTransactionDetails, email_2_accounts,
                         rate=1) -> Tuple[ExactTransactionLine, Decimal]:
        """ Translate a PayPal transaction into a set of Exact bookings
            :param rate: euro_amount / foreign_amount

            The amounts are rounded such that VAT payable benefits
        """
        # A regular payment in euro's
        gb_sales, vat_percentage = self.config.determineAccountVat(transaction)
        base_comment = self.config.determineComment(transaction, gb_sales)
        note = self.config.determineNote(transaction, gb_sales)
        transactiondate = transaction.Datum.date()

        # Use the following sequence:
        # First booking: the VAT return on the transaction fee (if any)
        # Second booking: the transaction fee (without VAT)
        # Third booking: the actual sale
        # Fourth booking: the VAT on the sale

        foreign_valuta = transaction.Valuta

        # Cache the results
        exact_log = None
        p = self.config.persist
        if p is not None:
            exact_log = p.exchangeTransactionLog(vat_percent=vat_percentage,
                                   account=gb_sales,
                                   amount=transaction.Bruto)

            p.paypalTransactionLog(exact_log,
                                   ref=transaction.Transactiereferentie,
                                   xref=transaction.ReferenceTxnID,
                                   timestamp=transaction.Datum)

        lines = []
        net_costs_euro = vat_costs_euro = Decimal('0.00')
        if transaction.Fee:
            # If the payment includes VAT, the VAT on the fee can be deducted
            # The gross amount equals 1.21 times the net amount, so dividing should get the net.
            net_costs = transaction.Fee
            net_costs_euro  = (net_costs*rate).quantize(Decimal('.01'), rounding=ROUND_UP)
            # The actual fee
            comment = 'Kosten ' + base_comment
            lines.append((transactiondate, self.config.costs_account, GLAccountTypes.SalesMarketingGeneralExpenses,
                         comment,
                          -net_costs_euro, self.config.currency, -net_costs, foreign_valuta, rate,
                         '<GLOffset code="%s" />'%self.config.pp_account, '', ''))
            lines.append((transactiondate, self.config.pp_account, GLAccountTypes.Bank,
                          comment,
                          net_costs_euro, self.config.currency, net_costs, foreign_valuta, rate,
                          '', '', ''))

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
        account = ''
        if gb_sales == self.config.creditors_kruispost:
            account = email_2_accounts.get(transaction.Naaremailadres, None)
            account_code = account.code if account else self.config.unknown_creditor
            account_type = GLAccountTypes.AccountsPayable
            account = '<Account code="%s" />'%account_code
        else:
            account_type = GLAccountTypes.Revenue
        lines.append((transactiondate, gb_sales, account_type,
                         comment,
                      -net_euro, self.config.currency, -net, foreign_valuta, rate,
                         additional,
                      account, note))
        lines.append((transactiondate, self.config.pp_account, GLAccountTypes.Bank,
                         comment,
                      net_euro, self.config.currency, net, foreign_valuta, rate,
                         additional,
                      account, note))

        # The VAT over the sale
        if vat_euro != Decimal('0.00'):
            comment = 'BTW ' + base_comment
            lines.append((transactiondate, self.config.vat_account, GLAccountTypes.General,
                          comment,
                          -vat_euro, self.config.currency, -vat, foreign_valuta, rate,
                             '<GLOffset code="%s" />'%self.config.pp_account, '', ''))
            lines.append((transactiondate, self.config.pp_account, GLAccountTypes.Bank,
                          comment,
                          vat_euro, self.config.currency, vat, foreign_valuta, rate,
                             '', '', ''))

        lines = [ExactTransactionLine(*l) for l in lines]

        return lines, transaction.Saldo

        exact_transaction = ExactTransaction(transaction.Datum, self.config.ledger, lines,
                                       transaction.Saldo)
        return exact_transaction, exact_log

    def make_foreign_transaction(self, transactions: List[PPTransactionDetails], email_2_accounts):
        # Get the details from the original transaction
        s = [t for t in transactions if
                    t.Type != 'Algemeen valutaomrekening' and t.Valuta != self.config.currency]
        if not s:
            logging.warning('Could not find original transaction, %s' % transactions)
            raise RuntimeError('Could not find original transaction')
        sale:PPTransactionDetails = s[0]
        s = [t for t in transactions if
                    t.Type == 'Algemeen valutaomrekening' and t.Valuta == self.config.currency]
        if not s:
            logging.warning('Ignoring conversion between foreign valuta, %s' % transactions)
            return None
        valuta_details:PPTransactionDetails = s[0]
        s = [t for t in transactions if
                   t.Type == 'Algemeen valutaomrekening' and t.Valuta != self.config.currency]
        if not s:
            logging.warning('Could not find foreign valuta part, %s' % transactions)
            raise RuntimeError('Could not find foreign valuta part')
        foreign_details:PPTransactionDetails = s[0]
        # Check the right transactions were found
        assert valuta_details.ReferenceTxnID == sale.ReferenceTxnID or sale.Transactiereferentie
        assert foreign_details.ReferenceTxnID == sale.ReferenceTxnID or sale.Transactiereferentie

        # Paypal converts the net amount of foreign money into the gross amount of local money
        rate = (valuta_details.Bruto / -foreign_details.Net).quantize(Decimal('.0000001'), rounding=ROUND_HALF_UP)

        lines, saldo = self.make_transaction(sale, email_2_accounts, rate)

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
                         '<GLOffset code="%s" />'%self.config.pp_account, ''),
                     (transactiondate, self.config.pp_account, GLAccountTypes.Bank,
                      comment,
                      -diff_euros, self.config.currency, -diff, foreign_valuta, rate,
                      '', '')
                     ]
            lines.extend([ExactTransactionLine(*l, '') for l in extra])
            logging.warning('Paypal left some foreign species on the account, %s'%diff)

        return lines, valuta_details.Saldo

        exact_transaction.closingbalance = valuta_details.Saldo
        return exact_transaction


    def groupedDetailsGenerator(self, fname, email_2_accounts):
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
                    print("Completed period %s: %s transactionlines"%(current_period, len(lines)),
                          file=sys.stderr)
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
                    if txs and txs[0].Datum != transaction.Datum:
                        txs = conversions_stack[ref] = [transaction]
                    else:
                        txs.append(transaction)
                    if len(txs) == 3:
                        foreign_details = self.make_foreign_transaction(txs, email_2_accounts)
                        if foreign_details:
                            new_lines, saldo = foreign_details
                            lines.extend(new_lines)
                        del conversions_stack[ref]
                else:
                    new_lines, saldo = self.make_transaction(transaction, email_2_accounts)
                    # If this account is not in euro's, set the exchange rate to -1 (unknown)
                    for l in new_lines:
                        l.ConversionRate = -1
                    lines.extend(new_lines)

            if lines:
                yield ExactTransaction(self.config.ledger, lines, saldo)
        except:
            traceback.print_exc()

    def detailsGenerator(self, fname):
        """ Generator that reads a list of PayPal transactions, and yields ExactTransactions """
        conversions_stack = {}  # Used to find the three transactions related to a valuta conversion
        try:
            # Download the PayPal Transactions
            reader = pp_reader(fname)
            transaction: PPTransactionDetails
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
                        lines, saldo = self.make_foreign_transaction(txs)
                        yield ExactTransaction(self.config.ledger, lines, saldo)
                        del conversions_stack[ref]
                else:
                    lines, saldo = self.make_transaction(transaction)
                    yield ExactTransaction(self.config.ledger, lines, saldo)

        except StopIteration:
            return
        except Exception as e:
            traceback.print_exc()
            raise


    def convertTransactions(self, pp_fname) -> Tuple[List[ExactTransaction], str]:
        """ Convert a paypal transaction """
        transactions: List[ExactTransaction] = list(self.groupedDetailsGenerator(pp_fname))

        # If there are no transactions, quit
        if len(transactions) == 0:
            return

        xml = self.generateExactTransactionsFile(transactions)

        return transactions, xml


def ZekeClassifier(path, details: dict):
    db = db_api.the_db = db_api.orm.Database()
    from admingen.clients import zeke
    instance = zeke.ZekeClassifier()
    db_api.openDb('sqlite://%s/zeke_data.db'%path)
    icp_files = glob.glob(path+'/*icp*.csv')
    transaction_files = glob.glob(path+'/*invoices*.csv')
    with db_api.sessionScope():
        instance.readTransactions(icp_files, transaction_files, details)

    def zeke_classifier(transaction: PPTransactionDetails):
        """ Let the Zeke client classify a PayPal transaction """
        match = order_nr_re.match(transaction.Factuurnummer)
        if match:
            order_nr = match.groups()[0]
            return instance.classifySale(order_nr)
        return SalesType.Unknown

    def getBtwAccount(transaction: PPTransactionDetails):
        """ Let the Zeke client classify a PayPal transaction """
        match = order_nr_re.match(transaction.Factuurnummer)
        if match:
            order_nr = match.groups()[0]
            return instance.getBtwAccount(order_nr)
        return None

    # I love Python! Might be more maintainable to use a proper class though...
    zeke_classifier.getBtwAccount = getBtwAccount

    return zeke_classifier


classifiers = {'Zeke': ZekeClassifier}


def handleDir(path, task_index):
    import glob
    from admingen.data import DataReader
    home = path+'/task_%i'%task_index

    paypals = glob.glob(home+'/Download*.CSV')
    with open(home+'/Accounts_1.xml') as f:
        accounts = processAccounts(f)
    data = DataReader('/home/ehwaal/admingen/projects/paypal_exact/taskconfig.csv')
    config = data['TaskConfig'][task_index]
    config = paypal_export_config(**config.__dict__)

    email_2_accounts = {email: account for account in accounts for email in account.email}

    classifier_config = data['Classifier'].get(task_index, None)
    if classifier_config:
        name = classifier_config.classifier_name
        config.classifier = classifiers[name](home, classifier_config.details)

    for i, fname in enumerate(paypals):
        converter = PaypalExactConverter(config)
        transactions = converter.groupedDetailsGenerator(fname, email_2_accounts)
        ofname = os.path.dirname(fname) + '/upload_%s.xml'%(i+1)
        with open(ofname, 'w') as of:
            converter.generateExactTransactionsFile(transactions, of)



def group_currency_conversions(transactions, config):
    """ Generator that reads a list of PayPal transactions, and yields ExactTransactions """
    conversions_stack = {}  # Used to find the three transactions related to a valuta conversion
    # Download the PayPal Transactions
    transaction: PPTransactionDetails
    # For each transaction, extract the accounting details
    for transaction in transactions:
        # Skip memo transactions.
        if transaction.Effectopsaldo and transaction.Effectopsaldo.lower() == 'memo':
            continue
        if transaction.TT == TT.CurrencyConversion or \
           transaction.Valuta != config.currency:
            # We need to compress the next three transactions into a single, foreign valuta one.
            # The actual transaction is NOT a conversion and is in foreign valuta.
            # The two conversions refer to this transaction
            if transaction.TT not in [TT.CurrencyConversion, TT.Refund, TT.BankDeposit, TT.Reversal]:
                ref = transaction.Transactiereferentie
            else:
                ref = transaction.ReferenceTxnID
            txs = conversions_stack.setdefault(ref, [])
            txs.append(transaction)
            if len(txs) == 3:
                # Classify the transactions and extract the useful bits
                s = [t for t in txs if
                     t.TT != TT.CurrencyConversion and t.Valuta != config.currency]
                if not s:
                    logging.warning('Could not find original transaction, %s' % txs)
                    raise RuntimeError('Could not find original transaction')
                sale: PPTransactionDetails = s[0]
                s = [t for t in txs if
                     t.TT == TT.CurrencyConversion and t.Valuta == config.currency]
                if not s:
                    logging.warning('Ignoring conversion between foreign valuta, %s' % txs)
                    txs = []
                    continue
                valuta_details: PPTransactionDetails = s[0]
                s = [t for t in txs if
                     t.TT == TT.CurrencyConversion and t.Valuta != config.currency]
                if not s:
                    logging.warning('Could not find foreign valuta part, %s' % transactions)
                    raise RuntimeError('Could not find foreign valuta part')
                foreign_details: PPTransactionDetails = s[0]
                # Check the right transactions were found
                assert valuta_details.ReferenceTxnID == sale.ReferenceTxnID or sale.Transactiereferentie
                assert foreign_details.ReferenceTxnID == sale.ReferenceTxnID or sale.Transactiereferentie

                sale.ConversionRate = (valuta_details.Bruto / -foreign_details.Net).quantize(Decimal('.0000001'), rounding=ROUND_HALF_UP)
                # The conversion rate goes from own currency to foreign currency
                sale.RemainderForeign = sale.Net + foreign_details.Bruto
                sale.Remainder = sale.RemainderForeign * sale.ConversionRate
                sale.ForeignValuta = sale.OriginalValuta = sale.Valuta
                sale.Valuta = valuta_details.Valuta
                sale.NetForeign = sale.NetOriginal = sale.Net
                sale.Net *= sale.ConversionRate
                sale.BrutoForeign = sale.Bruto
                sale.Bruto *= sale.ConversionRate
                sale.FeeForeign = sale.Fee
                sale.Fee *= sale.ConversionRate
                sale.Saldo = valuta_details.Saldo
                if sale.Remainder:
                    print('Remainder found:', sale.Remainder, sale)

                yield sale

                del conversions_stack[ref]
        else:
            # Close any incomplete currency exchanges
            for txs in conversions_stack.values():
                # If the transaction is too old (older than a day), throw it away
                for t in txs:
                    if t.Datum != transaction.Datum:
                        logging.warning('Incomplete money exchange found: %s' % txs[0])
                        # Find any transaction changing the relevant saldo
                        if t.Valuta == config.currency:
                            yield t
                        txs.remove(t)
            yield transaction

    # Clean up remaining currency exchanges.
    for txs in conversions_stack.values():
        if not txs:
            continue
        logging.warning('Incomplete money exchange found: %s' % txs[0])
        # If the transaction is too old (older than a day), throw it away
        for t in txs:
            # Find any transaction changing the relevant saldo
            if t.Valuta == config.currency:
                yield t


if __name__ == '__main__':
    handleDir('/home/ehwaal/tmp/pp_export/test-data', 1)
    sys.exit(0)


    from admingen.data import DataReader

    with open('/home/ehwaal/tmp/pp_export/test-data/twease/Accounts_1.xml') as f:
        accounts = processAccounts(f)
    email_2_accounts = {email:account for account in accounts for email in account.email}

    data = DataReader('/home/ehwaal/admingen/projects/paypal_exact/taskconfig.csv')
    config = data['TaskConfig'][1]
    config = paypal_export_config(**config.__dict__)
    converter = PaypalExactConverter(config)
    if False:
        testtrans = '''"Date","Time","TimeZone","Name","Type","Status","Currency","Gross","Fee","Net","From Email Address","To Email Address","Transaction ID","Shipping Address","Address Status","Item Title","Item ID","Shipping and Handling Amount","Insurance Amount","Sales Tax","Option 1 Name","Option 1 Value","Option 2 Name","Option 2 Value","Reference Txn ID","Invoice Number","Custom Number","Quantity","Receipt ID","Balance","Address Line 1","Address Line 2/District/Neighborhood","Town/City","State/Province/Region/County/Territory/Prefecture/Republic","Zip/Postal Code","Country","Contact Phone Number","Subject","Note","Country Code","Balance Impact"
"01/01/2017","22:55:16","CET","Avangate B.V.","Express Checkout Payment","Completed","USD","-470.25","0.00","-470.25","info@tim-productions.tv","paypal@avangate.com","2Y150470VV899273M","","Non-Confirmed","telestream.net purchase (Order #55659461)","","0.00","","0.00","","","","","30L77916RN3828012","55659461","","1","","-470.25","","","","","","","","telestream.net purchase (Order #55659461)","","","Debit"
'''
        test1 = StringIO(testtrans)
        transactions = converter.groupedDetailsGenerator(test1, email_2_accounts, None)
    else:
        testfname = '/home/ehwaal/tmp/pp_export/test-data/123products/Download.CSV'
        transactions = converter.groupedDetailsGenerator(testfname, email_2_accounts, None)
    if False:
        converter.generateExactTransactionsFile(transactions, sys.stdout)
    else:
        fname = 'test_transactions.xml'
        with open(fname, 'w') as of:
            converter.generateExactTransactionsFile(transactions, of)

