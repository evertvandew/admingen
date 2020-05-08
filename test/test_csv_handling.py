""" Test the extended CSV handling """

from dataclasses import dataclass
from enum import Enum
from datetime import datetime, date
from decimal import Decimal
import io
from admingen.data import CsvTableReader, CsvTableWriter
import unittest

example_csv_1 = r'''nummer:int,beschrijving:str,type_cd:CreditDebit,type_balans:BalansWinstVerlies
1000,Rek Courant,debit,balans
1001,Spaarrekening,debit,balans
1300,Debiteuren,debit,balans
1301,Onderhanden_Werk,debit,balans
1302,Privee_onttrekkingen,debit,balans
1600,BTW Aftedragen,credit,balans
1601,Inleg Eigenaar,credit,balans
1602,Crediteuren Algemeen,credit,balans
1603,Eigen_Vermogen,credit,balans
1604,Pensioen Opbouw,credit,balans
'''

example_csv_2 = r'''timestamp:formatted_date("%d%m%Y"),bedrag:Decimal,grootboek:int,omschrijving:str,reference:str
11012018,1355.2,1300,Factuur 2017001121\d 11012018\nescape \\ test\tja,2017001121
11012018,235.2,1600,Factuur 2017001121\d 11012018,2017001121
11012018,1120,8001,Factuur 2017001121\d 11012018,2017001121
05022018,1355.2,1300,Factuur 2018001011\d 05022018,2018001011
05022018,235.2,1600,Factuur 2018001011\d 05022018,2018001011
05022018,1120,8001,Factuur 2018001011\d 05022018,2018001011
'''

class enum_type:
    def __init__(self, name, options):
        self.annotation = name
        self.my_enum = Enum(name, options)
        self.my_enum.__str__ = lambda self: self.name
    def __call__(self, x):
        if type(x) == self.my_enum:
            return x
        return self.my_enum[x]
    def __getattr__(self, key):
        return self.my_enum[key]


CreditDebit = enum_type('CreditDebit', 'credit debit')
BalansWinstVerlies = enum_type('BalansWinstVerlies', 'balans winstverlies')

if False:
    if isinstance(args[0], str):
        dt = datetime.strptime(x, fmt)
    datettime.__init__(dt)


def formatted_date(fmt):
    """ Custom converter class for dates."""
    class MyDate:
        annotation = f'formatted_date("{fmt}")'
        def __init__(self, x):
            if type(x).__name__ == 'MyDate':
                self.dt = x.dt
            else:
                self.dt = datetime.strptime(x, fmt)
            self.fmt = fmt
        def __str__(self):
            return self.dt.strftime(self.fmt)
    return MyDate


DASH = '-'

def date_or_dash(fmt):
    """ Custom converter for either a dash ('-') or a formatted date. """
    class MyDate(formatted_date(fmt)):
        annotation = f'date_or_dash("{fmt}")'
        def __init__(self, x):
            if isinstance(x, str) and x == '-':
                self.dt = DASH
            else:
                super().__init__(x)
        def __str__(self):
            if self.dt == DASH:
                return self.dt
            return self.dt.strftime(self.fmt)
    return MyDate


def grootboek_key(key):
    return key.lower().replace(' ', '_')



@dataclass
class Grootboek:
    nummer: int
    beschrijving: str
    type_cd: CreditDebit
    type_balans: BalansWinstVerlies

@dataclass
class Transaction:
    timestamp: formatted_date('%d%m%Y')
    bedrag: Decimal
    grootboek: int
    omschrijving: str
    reference: str

class test(unittest.TestCase):
    def testReadWrite(self):
        for data, target in [(example_csv_1, Grootboek),
                             (example_csv_2, Transaction)]:
            stream = io.StringIO(data)
            records = list(CsvTableReader(stream, target))
            ostream = io.StringIO()
            CsvTableWriter(ostream, records)
            data2 = ostream.getvalue()
            if data2 != data:
                open('original.csv', 'w').write(data)
                open('reproduced.csv', 'w').write(data2)
            self.assertEqual(ostream.getvalue(), data)
    def testProcess(self):
        """ Test of er gerekend kan worden met de ingelezen waarden. """
        stream = io.StringIO(example_csv_2)
        records = list(CsvTableReader(stream, Transaction))
        total = sum([r.bedrag for r in records])
        self.assertEqual(total, Decimal('5420.8'))
    def testEscaping(self):
        """ Test the known instances of escaping are handled properly. """
        stream = io.StringIO(example_csv_2)
        records = list(CsvTableReader(stream, Transaction))
        self.assertEqual(records[0].omschrijving,
                         'Factuur 2017001121, 11012018\nescape \\ test\tja')