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
from admingen.clients.rest import OAuth2
from admingen.clients.exact_xml import XMLapi, logging, TransactionLine
from admingen.keyring import KeyRing
from admingen.clients.rest import OAuth2, OAuthDetails, FileTokenStore
from csv import DictWriter


# TODO: afmaken

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


pw = input('Please give password for oauth keyring')
ring = KeyRing('oauthring.enc', pw)
details = ring['exact_secrets_1']
details = OAuthDetails(**details)
oa = OAuth2(FileTokenStore('../paypal_exact/exacttoken_1.json'), details, ring.__getitem__)
api = XMLapi(oa)
divisions = api.getDivisions()


with open('test.csv', 'w') as f:
    w = DictWriter(f,
                   fieldnames=['administratie', 'admincode'] + [f.name for f in fields(TransactionLine)],
                   delimiter=';')
    w.writeheader()

    for division in divisions:
        logging.getLogger().debug('Downloading administration %s'%division)
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
            w.writerow(details)
