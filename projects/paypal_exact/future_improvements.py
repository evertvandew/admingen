#!/usr/bin/env python3
"""
Compare with old uploads using:
set filter="(Rate)|(GLTransactionLine)|(Transactie)"; diff -bB <(egrep -v "$filter" ~/admingen/projects/paypal_exact/test.xml) <(egrep -v "$filter" pp_export/test-data/task_1/upload2018.xml) | less
"""
from decimal import Decimal, ROUND_HALF_UP
import datetime
from dataclasses import dataclass
import xml.etree.ElementTree as ET
import xml.dom.minidom as dom
import sys
import csv
import re
import argparse
import os.path
from dataclasses import asdict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from admingen.clients.exact_xml import findattrib
from admingen.data import DataReader, CsvWriter
from admingen.data import dataset
from admingen.clients.paypal import pp_reader
from paypal_converter import (paypal_export_config, SalesType, group_currency_conversions,
                              classifiers, match_transaction_type, TransactionTypes,
                              add_transactionTypes, filter_foreign_references)


# TODO: Bij de configuratie ook dicts & lists ondersteunen?


vat_name = 'VATs_1.xml'


# TODO: let the dataclass automatically cast data to the right types.
@dataclass
class VatDetails:
    code: int
    type: str
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
    # The script exchange_rates will do that.
    reader = csv.reader(open('/home/ehwaal/tmp/pp_export/test-data/eurofxref-hist.csv'))
    # Create a lookup table for determining the right exchange rate.
    keys = next(reader)
    data = {}
    matcher = re.compile(r'[0-9.]+')
    for line in reader:
        conversions = {k: Decimal(e) for k, e in zip(keys[1:], line[1:]) if matcher.match(e)}
        d = datetime.datetime.strptime(line[0], '%Y-%m-%d').date()
        data[d] = conversions

    def getRate(d, currency):
        """ Retrieve the conversion rate from the foreign currency to EUR,
            based on the daily settlement rates published by the European Central Bank.
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


def checker(groupedtransactions, xml, config):
    root = ET.fromstring(xml)

    # First check: the main saldo.
    first = groupedtransactions[0][0]
    saldo = first.Saldo - first.Net + getattr(first, 'Remainder', 0)

    for transactions, glt in zip(groupedtransactions, root.findall('.//GLTransaction')):
        for line in glt.findall('.//GLTransactionLine'):
            if line.find('GLAccount').attrib['code'] == "%s" % config.pp_account:
                index = int((int(line.attrib['line'])-1)/3)
                if config.currency == 'EUR':
                    amount = Decimal(line.find('./Amount/Value').text)
                    saldo += amount
                else:
                    saldo += Decimal(line.find('./ForeignAmount/Value').text)
                t = transactions[index]

                offset = (int(line.attrib['line'])-1) % 3
                if getattr(t, 'Remainder', 0):
                    checknow = offset == 2
                elif t.Fee:
                    checknow = offset == 1
                else:
                    checknow = True

                if checknow:
                    # The saldo should be equal to the end saldo in the transaction.
                    if saldo != t.Saldo:
                        print("SALDO ERROR:", saldo, t.Saldo, saldo-t.Saldo, t)
                        saldo = t.Saldo

    # Second check: transaction balance
    # We check the balance for all transactionlines with the same line number.
    for glt in root.findall('.//GLTransaction'):
        nr = '0'
        saldo = Decimal(0)
        for line in glt.findall('GLTransactionLine'):
            if line.attrib['line'] != nr:
                if saldo != Decimal(0):
                    print('BALANCE ERROR', saldo, 'Before', line)
                    saldo = Decimal(0)
            nr = line.attrib['line']
            if config.currency == 'EUR':
                saldo += Decimal(line.find('./Amount/Value').text)
            else:
                d = line.find('./ForeignAmount/Value')
                if d:
                    saldo += Decimal(d.text)
        if saldo != Decimal(0):
            print('BALANCE ERROR', saldo, 'In', line)

    # Third check: for non-euro accounts also check the balance in the euro parts
    if False and config.currency != 'EUR':
        for glt in root.findall('.//GLTransaction'):
            nr = '0'
            saldo = Decimal(0)
            error = 0
            for line in glt.findall('GLTransactionLine'):
                if line.attrib['line'] != nr:
                    error += saldo - Decimal(0)
                    if saldo != Decimal(0):
                        #print('FOREIGN BALANCE ERROR', saldo, 'Before', line)
                        saldo = Decimal(0)
                nr = line.attrib['line']
                fa = line.find('./ForeignAmount')
                if fa:
                    rate = Decimal(line.find('./ForeignAmount/Rate').text)
                    delta = Decimal(line.find('./ForeignAmount/Value').text) * rate
                    saldo += delta.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                else:
                    saldo += Decimal(line.find('./Amount/Value').text)
            error += saldo - Decimal(0)
            if error:
                print('FOREIGN BALANCE ERROR', error, 'In', line)
                print (ET.tostring(glt, method='xml').decode('utf8'))



def run(configpath, basedir, taskid, ofname, ifname):
    # Read the configuration
    taskid = int(taskid)
    data = DataReader(configpath)
    config = paypal_export_config(**data['TaskConfig'][taskid])
    home = os.path.join(basedir, 'task_%i' % taskid)
    ifname = ifname or (home+'/Download.CSV')

    # Read the VAT details
    if config.handle_vat:
        root = ET.parse(os.path.join(home, vat_name))
        vatdetails = dataset((VatDetails(v.attrib['code'],
                                         v.attrib['type'],
                                         Decimal(v.find('Percentage').text),
                                         findattrib(v, 'GLToPay', 'code'),
                                         findattrib(v, 'GLToClaim', 'code'))
                              for v in root.findall('*/VAT')),
                             index='code')
        # Check all vat codes are of the 'Inclusief' type
        assert all(vatdetails[i].type in 'BI' for i in config.vat_codes.values())
    else:
        vatdetails = {}

    # Determine which VAT classifier to use
    classifier_def = data['Classifier'].get(taskid, None)
    if False and classifier_def:
        classifier = classifiers[classifier_def.classifier_name](home, classifier_def.details)
    else:
        classifier = config.getRegion

    ###############################################################################
    # Read and process the Paypal transactions
    # Process is performed by queries that add data to the transactions.

    pp_transactions = pp_reader(ifname)
    transactions = add_transactionTypes(pp_transactions)
    transactions = filter_foreign_references(transactions)
    transactions = dataset(group_currency_conversions(transactions, config))

    transactions.enrich(debitcredit=config.getType,
                        vatregion=classifier,
                        glaccount=config.getGLAccount,
                        glatype=config.getGLAType,
                        vatpercent=0)

    transactions.join(lambda t: vatdetails[config.vat_codes[t.vatregion]],
                      getupdate=lambda t, v: dict(
                          vatpercent=v.percentage,
                          vataccount=v.pay_gla if t.debitcredit == 'c' else v.claim_gla,
                          vatcode=v.code
                      ),
                      defaults=dict(vatpercent=0, vataccount=None, vatcode=None)
                      )

    # Fill-in the ICP details, where necessary
    if hasattr(classifier, 'getBtwAccount'):
        transactions.enrich_condition(
            condition='vatregion == SalesType.EU_ICP',
            true={'icpaccountnr': classifier.getBtwAccount},
            false=lambda t: {'icpaccountnr': None}
        )

    if config.currency != 'EUR':
        # Non-euro accounts present a problem, as accounts in Exact are always EUR accounts
        # with some support for handling non-EUR currencies. So we need to generate the necessary
        # conversions to Euro without having a conversion read from the actual transaction.
        def setDetails(t):
            date = t.Datum
            rate = 1 / getRate(date, t.Valuta)
            assert t.Valuta == config.currency
            result = dict(NetForeign=t.Net,
                        FeeForeign=t.Fee,
                        BrutoForeign=t.Bruto,
                        RemainderForeign=getattr(t, 'Remainder', Decimal(0)),
                        Net=(t.Net * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                        Fee=(t.Fee * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                        Remainder=(getattr(t, 'Remainder', Decimal(0)) * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                        ForeignValuta=t.Valuta,
                        Valuta='EUR',
                        ConversionRate=rate)
            # Ensure that rounding can not introduce 1-cent errors.
            result['Bruto'] = result['Net'] - result['Fee']
            return result

        # We need to add the details needed by Exact to handle the conversion to EUR.
        #transactions.enrich(setDetails)
        transactions.enrich(ConversionRate=lambda t: 1 / getRate(t.Datum, config.currency))

    # When handling sales through the creditors account, add an unknown creditor.
    transactions.enrich_condition(condition=lambda t: t.glaccount == config.creditors_kruispost,
                                  true=lambda t: {'Customer': config.unknown_creditor},
                                  false={'Customer': None})

    # Determine the note and comment texts
    transactions.enrich(Note=config.getNote,
                        Comment=config.getComment)


    # Group the transactions per month: a single transaction is produced for a month.
    # Do NOT group transactions in non-euro accounts: the round-off errors accumulate too much
    # and can not be compensated by Exact.

    if config.currency == 'EUR':
        grouped_transactions = list(group_per_period(transactions))
    else:
        grouped_transactions = [[t] for t in transactions]



    # Save the transactions for testing & comparison
    CsvWriter(open(home+'/test2.csv', 'w'), {'Transactions': transactions})

    ###############################################################################
    # Create the output file.
    # We use a Jinja2 template to create an XML file that can be loaded into Exact.
    env = Environment(loader=FileSystemLoader('.'),
                      autoescape=select_autoescape(['xml']),
                      line_statement_prefix='%',
                      line_comment_prefix='%%')

    env.globals.update(abs=abs,
                       Decimal=Decimal,
                       getattr=getattr,
                       enumerate=enumerate,
                       ROUND_HALF_UP=ROUND_HALF_UP,
                       len=len)

    try:
        template = env.get_template('exacttransactions.jinja')
    except Exception as e:
        e.translated = False
        print (str(e))
        raise
    xml = template.render(transactions=grouped_transactions, config=config)

    if ofname:
        with open(os.path.join(home, ofname), 'w') as out:
            out.write(xml)
    else:
        sys.stdout.write(xml)

    if transactions:
        checker(grouped_transactions, xml, config)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('-c', '--config',
                   default='/home/ehwaal/admingen/projects/paypal_exact/taskconfig.csv')
    p.add_argument('-b', '--basedir', default='/home/ehwaal/tmp/pp_export/test-data/')
    p.add_argument('-t', '--taskid', default='3')
    p.add_argument('-o', '--outfile', default='upload.xml')
    p.add_argument('-v', '--verify', action='store_true')
    p.add_argument('-f', '--infile', default=None)
    args = p.parse_args()
    run(args.config, args.basedir, args.taskid, args.outfile, args.infile)
