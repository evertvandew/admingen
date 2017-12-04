
from decimal import Decimal, ROUND_HALF_UP
import os.path
import xml.etree.ElementTree as ET
from unittest import TestCase, main
from paypal_exact.worker import PaypalExactTask, WorkerConfig, generateExactTransactionsFile


def as_csv(l):
    return ','.join(str(i) for i in l)


config = WorkerConfig(ledger=21,
                      costs_account=5561,
                      pp_account=1101,
                      debtors_account=1300,
                      creditors_account=1600,
                      pp_kruispost=2100)


class TestPayPalExport(TestCase):
    def testConversion(self):
        fname = os.path.join(os.path.dirname(__file__), 'pp_testdata.csv')
        converter = PaypalExactTask(None, config, None)

        # Check that the transactions are consistent
        saldo = Decimal('1875.88') - Decimal('49.87')
        for details in converter.detailsGenerator(fname):
            #print (details)
            #print (saldo)
            # Check the transaction connects to the previous saldo
            for l in details.lines:
                saldo = saldo + l.Amount if  l.GLAccount==1101 else saldo
            self.assertEqual(saldo, details.ClosingBalance)

            # Check the sum of all transaction lines is zero
            self.assertEqual(sum(l.Amount for l in details.lines), Decimal('0.00'))

            # Check the foreign amount times rate equals the euro amount
            for l in details.lines:
                self.assertEqual(l.Amount, (l.ForeignAmount * l.ConversionRate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

        # Check the final saldo
        self.assertEqual(saldo, Decimal('1201.28'))


    def testXmlGeneration(self):

        fname = os.path.join(os.path.dirname(__file__), 'pp_testdata.csv')
        converter = PaypalExactTask(None, config, None)
        xml = generateExactTransactionsFile(converter.detailsGenerator(fname))

        # Check that the result is valid XML
        dom = ET.fromstring(xml)
        # Check the number of transactions
        transactions = dom.findall('.//GLTransaction')
        count = sum(1 for _ in converter.detailsGenerator(fname))
        self.assertEqual(len(transactions), count)

        # check all lines add up to zero
        # This is a feature of having double booking accounts
        all_values = [Decimal(v.text) for v in dom.findall('.//Value')]
        total = sum(all_values)
        self.assertEqual(total, Decimal('0.00'))

        # Check all transactions on account 1101 add to the proper amount
        amounts = [t for t in dom.findall(".//GLAccount[@code='1101']../Amount/Value")]
        delta = Decimal('1201.28') - Decimal('1875.88') + Decimal('49.87')
        self.assertEqual(sum(Decimal(v.text) for v in amounts), delta)

        # This looks OK!








if __name__ == '__main__':
    main()
