#!/usr/bin/env python3
""" A tool / environment for analysing the data in exact.

Original idea:
Graag zou ik voor alle administraties binnen de exact omgeving alle mutaties iig
van 2017 en 2018 in 1 excel bestand de mutaties willen benaderen. Kan wat mij betreft
van alle bedrijven ook in 2 bestanden:
    1. alle grootboekrekening <#4000 (balans)
    2. >4000 (Winst- en verliesrekening).

Ik zou graag alle bestaande mutaties met nieuwe mutaties in 1 database bestand willen
hebben zodat ik hier een draaitabel op kan loslaten. Hierbij wil ik alle beschikbare
attributen die exact biedt in de kolommen beschikbaar willen hebben.


It seems that the easiest way to get data into access is to import a CSV file.
An alternative could be a local app that writes into ODBC.

"""

import sys
from dataclasses import asdict, fields
from argparse import ArgumentParser
import time
from admingen.clients.rest import OAuth2
from admingen.clients.exact_xml import XMLapi, logging, TransactionLine
from admingen.keyring import KeyRing
from admingen.clients.rest import OAuth2, OAuthDetails, FileTokenStore
from csv import DictWriter
from croniter import croniter


logging.getLogger().setLevel(logging.DEBUG)

if False:
    with open('/home/ehwaal/tmp/transactions.xml') as f:
        data = f.read()
    ts = parseTransactions(data)

    w = DictWriter(sys.stdout, fieldnames = asdict(ts[0]).keys(), delimiter=';')
    w.writeheader()
    for t in ts:
        details = asdict(t)
        for k in ['Amount', 'ForeignAmount']:
            a = str(details[k])
            a = a.replace(',', '_')
            a = a.replace('.', ',')
            a = a.replace('_', '.')
            details[k] = a
        w.writerow(details)

    sys.exit()

def download(ring, taskid):
    ringdetails = ring['exact_secrets_%i'%taskid]
    ringdetails = OAuthDetails(**ringdetails)
    oa = OAuth2(FileTokenStore('../paypal_exact/exacttoken_1.json'), ringdetails, ring.__getitem__)
    api = XMLapi(oa)
    divisions = api.getDivisions()

    results = []
    for division in divisions:
        logging.getLogger().debug('Downloading glaccounts for %s' % division)
        glaccounts = api.getGLAccounts(division.Code)
        glaccountsdict = {a.Code: a for a in glaccounts}
        logging.getLogger().debug('Downloading administration %s' % division)
        transactions = api.getTransactions(division.Code)
        for t in transactions:
            details = asdict(t)
            for k in ['Amount', 'ForeignAmount']:
                a = str(details[k])
                a = a.replace(',', '_')
                a = a.replace('.', ',')
                a = a.replace('_', '.')
                details[k] = a
            details['administratie'] = division.Description
            details['admincode'] = division.HID
            gla = glaccountsdict.get(t.GLAccountCode, None)
            if gla:
                details['classification'] = gla.Classification
                details['classpath'] = gla.Classpath
            else:
                details['classification'] = ''
                details['classpath'] = ''
            results.append(details)
    return results


if __name__ == '__main__':
    ap = ArgumentParser()
    ap.add_argument('--unix_socket', '-u', help='Unix Socket for receiving the keyring password', default='')
    ap.add_argument('--schedule', '-s', help='Schedule for activation, in cron syntax.', default='')
    ap.add_argument('--year', '-y', help='Year for which the transactions are retrieved. Default: running year', default=None)
    # TODO: Pass me along! (year)
    args = ap.parse_args()

    ringfile = 'oauthring.enc'
    if not args.unix_socket:
        pw = input('Please give password for oauth keyring')
        ring = KeyRing(ringfile, pw)
    else:
        ring = KeyRing.open_from_socket(ringfile, args.unix_socket)

    if args.schedule:
        schedule = croniter(args.schedule)
        wakeup = next(schedule)
    else:
        schedule = None
        wakeup = time.time()

    while True:
        while time.time() < wakeup:
            time.sleep(10)

        results = download(ring, 1)

        with open('test.csv', 'w') as f:
            w = DictWriter(f,
                           fieldnames=['administratie', 'admincode', 'classification', 'classpath'] + [f.name for f in fields(TransactionLine)],
                           delimiter=';')
            w.writeheader()

            for details in results:
                w.writerow(details)

        if schedule is None:
            break

        # Find a new activation time that we are not already past.
        while True:
            wakeup = next(schedule)
            # Only use this one if we are not already past it.
            if wakeup > time.time():
                break