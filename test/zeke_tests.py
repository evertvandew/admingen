from decimal import Decimal
from admingen.clients.zeke import readTransactions, ZekeDetails, ZekeAccount, ZekeTransaction
from admingen.db_api import sessionScope, the_db, select
from unittest import TestCase


class TestReading(TestCase):
    @classmethod
    def setUpClass(cls):
        the_db.bind(provider='sqlite', filename=':memory:')
        the_db.generate_mapping(create_tables=True)
    def testReading(self):
        fnames = ['zeke_test_files/export_icp_01-12-2017_01-01-2018.csv',
                  'zeke_test_files/export_invoices_01-12-2017_01-01-2018.csv']

        # Read the invoice details
        details = ZekeDetails(url='https://www.retrofitlab.com',
                              username='pietje_puk')

        with sessionScope():
            _ = ZekeAccount(**details)

        readTransactions(fnames, details)

        # Check that an ICP transaction was correctly read
        with sessionScope():
            t:ZekeTransaction = select(t for t in ZekeTransaction if t.order_nr==12817).first()
            self.assertTrue(t)
            self.assertEqual(t.btwcode, 'SE820809065701')
            self.assertEqual(t.countrycode, 'SE')
            self.assertEqual(t.gross, Decimal('134.62'))
            self.assertEqual(t.tax, Decimal('0.0'))
