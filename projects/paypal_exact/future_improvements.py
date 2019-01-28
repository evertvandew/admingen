from decimal import Decimal
from dataclasses import dataclass
from admingen.data import dataset
import xml.etree.ElementTree as ET
from paypal_converter import paypal_export_config, pp_reader, SalesType, group_currency_conversions
from typing import Dict
from admingen.clients.exact_xml import findattrib
from admingen.data import DataReader
from jinja2 import Environment, FileSystemLoader, select_autoescape
from scipy.interpolate import interp1d
import sys
import csv
import re
import datetime
import os.path


# TODO: er zit een GLOffset naar zichzelf bij een 1101 transactie.
# TODO: De note staat uit.
# TODO: De VAT onderdelen toevoegen en testen.



taskid = 2
vat_name = '/home/ehwaal/tmp/pp_export/test-data/task_%i/VATs_1.xml'%taskid
fname = '/home/ehwaal/tmp/pp_export/test-data/task_%i/Download.CSV'%taskid


data = DataReader('/home/ehwaal/admingen/projects/paypal_exact/taskconfig.csv')
config = paypal_export_config(**data['TaskConfig'][taskid])

if False:
    @dataclass
    class paypal_export_config:
        taskid: int
        customerid: int
        administration_hid: int
        ledger: str
        costs_account: str
        pp_account: str
        sale_accounts: Dict[SalesType, int]
        purchase_accounts: Dict[SalesType, int]
        purchase_needs_invoice: bool
        creditors_kruispost: str
        unknown_creditor: str
        pp_kruispost: str
        handle_vat: bool
        vat_codes: Dict[SalesType, int]
        currency: str


# Load the VAT configuration for this task

# TODO: let the dataclass automatically cast data to the right types.
@dataclass
class VatDetails:
    code: int
    percentage: Decimal
    pay_gla: int
    claim_gla: int


def group_per_period(transactions):
    previous = None
    group = []
    for t in transactions:
        t.linenr = len(group) + 1
        previous = previous or (t.Datum.year, t.Datum.month)
        current = (t.Datum.year, t.Datum.month)
        if current != previous:
            yield group
            group = [t]
            previous = current
        else:
            group.append(t)
    # Don't forget to yield the last transactions...
    yield group



def readConversionRates():
    # Load the current conversion table
    # Download the table from: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip
    reader = csv.reader(open('/home/ehwaal/tmp/pp_export/test-data/eurofxref-hist.csv'))
    # Create a lookup table for determining the right exchange rate.
    keys = next(reader)
    data = {}
    matcher = re.compile(r'[0-9.]+')
    for line in reader:
        conversions = {k:Decimal(e) for k, e in zip(keys[1:], line[1:]) if matcher.match(e)}
        d = datetime.datetime.strptime(line[0], '%Y-%m-%d').date()
        data[d] = conversions

    def getRate(d, currency):
        """ Retrieve the conversion rate from the foreign currency to EUR,
            based on the daily settlement rates published by the European Bank.
        """
        if isinstance(d, str):
            d = datetime.datetime.strptime(d, '%Y-%m-%d').date()
        elif isinstance(d, datetime.datetime):
            d = d.date()
        while True:
            table = data.get(d, None)
            if table:
                return table[currency]
            d -= datetime.timedelta(1, 0)
    return getRate

getRate = readConversionRates()



# Read the VAT details
if os.path.exists(vat_name):
    root = ET.parse(vat_name)
    vatdetails = dataset((VatDetails(v.attrib['code'],
                                     v.find('Percentage').text,
                                     findattrib(v, 'GLToPay', 'code'),
                                     findattrib(v, 'GLToClaim', 'code'))
                          for v in root.findall('*/VAT')),
                         index='code')
else:
    vatdetails = {}


###############################################################################
# Read and process the Paypal transactions
# Process is performed by queries that add data to the transactions.

pp_transactions = pp_reader(fname)
transactions = dataset(group_currency_conversions(pp_transactions, config)) \
    .enrich(debitcredit=config.getType,
            vatregion=config.getRegion,
            glaccount=config.getGLAccount,
            glatype=config.getGLAType,
            template=config.getTemplate) \
    .join(lambda t: vatdetails[config.vat_codes[t.vatregion]],
          getupdate=lambda t, v: dict(
              vatpercent=v.percentage,
              vataccount=v.pay_gla if t.debitcredit == 'c' else v.claim_gla
          ),
          defaults=dict(vatpercent=0, vataccount=None)
          )


if config.currency != 'EUR':
    # Non-euro accounts present a problem, as accounts in Exact are always EUR accounts
    # with some support for handling non-EUR currencies. So we need to generate the necessary
    # conversions to Euro without having a conversion read from the actual transaction.
    def setDetails(t):
        date = t.Datum
        rate = getRate(date, t.Valuta)
        assert t.Valuta == config.currency
        return dict(NetForeign=t.Net,
                    FeeForeign=t.Fee,
                    BrutoForeign=t.Bruto,
                    Net=None,
                    Fee=None,
                    Bruto=None,
                    ForeignValuta=t.Valuta,
                    ConversionRate=rate,
                    RemainderForeign=getattr(t, 'Remainder', Decimal('0')) * rate)


    # We need to add the details needed by Exact to handle the conversion to EUR.
    if False:
        transactions.enrich_condition(
        condition=lambda t: not hasattr(t, 'ForeignAmount'),
        true=setDetails
    )
    transactions.enrich(setDetails)

# Calculate the VAT elements
transactions.enrich_condition(
    condition=lambda t: t.Type == 'd' or (t.Type == 'c' and not config.purchase_needs_invoice),
    true=lambda t: {'Vat': t.Net * t.percentage,
                    'AfterVat': t.Net - t.Vat},
    false=lambda t: {'Vat': Decimal('0.00'), 'AfterVat': t.Net}
    )


transactions.enrich_condition(condition=lambda t: t.glaccount == config.creditors_kruispost,
                              true=lambda t: {'Customer': config.unknown_creditor},
                              false={'Customer': None})
transactions.enrich(Note=config.getNote,
                    Comment=config.getComment)

grouped_transactions = list(group_per_period(transactions))


###############################################################################
# Create the output file.
# We use a Jinja2 template to create an XML file that can be loaded into Exact.
env = Environment(loader=FileSystemLoader('.'),
                  autoescape=select_autoescape(['xml']),
                  line_statement_prefix='%',
                  line_comment_prefix='%%')

env.globals.update(abs=abs, Decimal=Decimal, getattr=getattr)

template = env.get_template('exacttransactions.jinja')
sys.stdout.write(template.render(transactions=grouped_transactions, config=config))
with open('test.xml', 'w') as out:
    out.write(template.render(transactions=grouped_transactions, config=config))
