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

vat_name = '/home/ehwaal/tmp/pp_export/test-data/task_1/VATs_1.xml'
fname = '/home/ehwaal/tmp/pp_export/test-data/task_1/Download2018.CSV'

data = DataReader('/home/ehwaal/admingen/projects/paypal_exact/taskconfig.csv')
config = paypal_export_config(**data['TaskConfig'][1])

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


# Read the VAT details
root = ET.parse(vat_name)
vatdetails = dataset((VatDetails(v.attrib['code'],
                                 v.find('Percentage').text,
                                 findattrib(v, 'GLToPay', 'code'),
                                 findattrib(v, 'GLToClaim', 'code'))
                      for v in root.findall('*/VAT')),
                     index='code')

# Read the Paypal
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

USD_conversions = interp1d


def getRate(date, currency):
    pass


if config.currency != 'EUR':
    # Non-euro accounts present a problem, as accounts in Exact are always EUR accounts
    # with some support for handling non-EUR currencies. So we need to generate the necessary
    # conversions to Euro without having a conversion read from the actual transaction.
    def setDetails(t):
        return dict(NetForeign=t.Net,
                    FeeForeign=t.Fee,
                    BrutoForeign=t.Bruto,
                    Net=None,
                    Fee=None,
                    Bruto=None,
                    ForeignValuta=t.Valuta,
                    ConversionRate=Decimal('1'))


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


env = Environment(loader=FileSystemLoader('.'),
                  autoescape=select_autoescape(['xml']),
                  line_statement_prefix='%',
                  line_comment_prefix='%%')

env.globals.update(abs=abs)

template = env.get_template('exacttransactions.jinja')
sys.stdout.write(template.render(transactions=grouped_transactions, config=config))
with open('test.xml', 'w') as out:
    out.write(template.render(transactions=grouped_transactions, config=config))
