#!/usr/bin/env python3
""" Analyse the transactions in PayPal to determine the currency of the account. """

from decimal import Decimal
from admingen.clients.paypal import pp_reader



fname = '/home/ehwaal/tmp/pp_export/test-data/task_4/Download.CSV'

currencies = {}


# Determine to which currency transactions are converted
from_currencies = {}
to_currencies = {}
for t in pp_reader(fname):
    if t.Type == 'Algemeen valutaomrekening' and t.Saldo == Decimal('0.00'):
        from_currencies[t.ReferenceTxnID] = t.Valuta

for t in pp_reader(fname):
    if t.ReferenceTxnID in from_currencies and t.Saldo != Decimal('0.00'):
        currencies[t.Valuta] = currencies.get(t.Valuta, 0) + 1
        to_currencies[t.ReferenceTxnID] = t.Valuta

# Count from and to which valuta are converted
fromto_conversions = {}
for k, vf in from_currencies.items():
    pair = (vf, to_currencies[k])
    fromto_conversions[pair] = fromto_conversions.get(pair, 0) + 1


print(currencies)
print(fromto_conversions)
