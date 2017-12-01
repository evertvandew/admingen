
from decimal import Decimal, ROUND_HALF_UP
import os.path
from unittest import TestCase, main
from paypal_exact.worker import PaypalExactTask, WorkerConfig, generateExactTransaction


def as_csv(l):
    return ','.join(str(i) for i in l)


class TestPayPalExport(TestCase):
    def testConversion(self):
        config = WorkerConfig(ledger=21,
                              costs_account=5561,
                              pp_account=1101,
                              debtors_account=1300,
                              creditors_account=1600,
                              pp_kruispost=2100)

        fname = os.path.join(os.path.dirname(__file__), 'pp_testdata.csv')
        converter = PaypalExactTask(None, config, None)
        xml_lines = [generateExactTransaction(details) \
                     for details in converter.detailsGenerator(fname)]

        # Check that the result is valid XML
        # TODO

        # Check that the transactions are consistent
        saldo = Decimal('1875.88') - Decimal('49.87')
        for details in converter.detailsGenerator(fname):
            print (details)
            #print (saldo)
            if details.ClosingBalance == Decimal('273.82'):
                print ('ho')
            # Check the transaction connects to the previous saldo
            for l in details.lines:
                saldo = saldo + l.Amount if  l.GLAccount==1101 else saldo
            if saldo != details.ClosingBalance:
                print ('ho')
            self.assertEqual(saldo, details.ClosingBalance)

            # Check the sum of all transaction lines is zero
            self.assertEqual(sum(l.Amount for l in details.lines), Decimal('0.00'))

            # Check the foreign amount times rate equals the euro amount
            for l in details.lines:
                self.assertEqual(l.Amount, (l.ForeignAmount * l.ConversionRate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

        self.assertEqual(saldo, Decimal('1201.28'))



if __name__ == '__main__':
    main()
