
from decimal import Decimal, ROUND_HALF_UP
import os.path
import xml.etree.ElementTree as ET
from unittest import TestCase, main
from io import StringIO
import re

from paypal_exact.worker import PaypalExactTask, WorkerConfig, generateExactTransactionsFile, PPTransactionDetails, zeke_classifier
from admingen.clients import zeke
from admingen.db_api import the_db, sessionScope, select
from admingen.dataclasses import asdict
from admingen.international import SalesType


def as_csv(l):
    return ','.join(str(i) for i in l)


config = WorkerConfig(ledger=21,
                      costs_account=5561,
                      pp_account=1101,
                      sale_account_nl=8000,
                      sale_account_eu_no_vat=8100,
                      sale_account_world=8101,
                      sale_account_eu_vat=8102,
                      purchase_account_nl=7100,
                      purchase_account_eu_no_vat=7101,
                      purchase_account_world=7102,
                      purchase_account_eu_vat=7103,
                      pp_kruispost=2100,
                      vat_account=1514)


# In PayPal, the order_nr has a strange string prepended ('papa xxxx')
# Define an RE to strip it.
order_nr_re = re.compile(r'\D+(\d+)')

class TestPayPalExport(TestCase):
    @classmethod
    def setUpClass(cls):
        the_db.bind(provider='sqlite', filename=':memory:', create_db=True)
        the_db.generate_mapping(create_tables=True)

    def testConversion(self):
        fname = os.path.join(os.path.dirname(__file__), 'pp_testdata.csv')
        converter = PaypalExactTask(('pietje_puk', 'mijn_password'), config, None)

        # Check that the transactions are consistent
        saldo = Decimal('1875.88') - Decimal('49.87')
        for details in converter.detailsGenerator(fname):
            #print (details)
            #print (saldo)
            # Check the transaction connects to the previous saldo
            for l in details.lines:
                saldo = saldo + l.Amount if  l.GLAccount==1101 else saldo
            print ('Expected saldo:', details.closingbalance)
            self.assertEqual(saldo, details.closingbalance)

            # Check the sum of all transaction lines is zero
            self.assertEqual(sum(l.Amount for l in details.lines), Decimal('0.00'))

            # Check the foreign amount times rate equals the euro amount
            # As not all amounts are rounded in the same direction, allow an error of 2 cents.
            for l in details.lines:
                self.assertLess(abs(l.Amount - (l.ForeignAmount * l.ConversionRate)), 0.02)

            # Check the BTW amounts, depending on the number of lines returned.
            pairs = []
            if len(details.lines) == 8:
                # VAT and costs, so two checks
                pairs = [[0, 2], [6, 4]]
            if len(details.lines) == 4 and details.lines[0].GLAccount!=5561:
                # Only VAT, no costs, one check.
                pairs = [[2, 0]]
            for a, b in pairs:
                diff = details.lines[a].Amount - details.lines[b].Amount * Decimal('0.21')
                # Allow 2 cents difference, due to rouding effects
                self.assertLess(abs(diff), 0.02)

        # Check the final saldo
        self.assertEqual(saldo, Decimal('1201.28'))


    def testXmlGeneration(self):

        fname = os.path.join(os.path.dirname(__file__), 'pp_testdata.csv')
        converter = PaypalExactTask(('pietje_puk', 'mijn_password'), config, None)
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

    def testGeneration(self):
        f = StringIO("""Datum,Tijd,Tijdzone,Naam,Type,Status,Valuta,Bruto,Fee,Net,Van e-mailadres,Naar e-mailadres,Transactiereferentie,Verzendadres,Status adres,Item Title,Objectreferentie,Verzendkosten,Verzekeringsbedrag,Sales Tax,Naam optie 1,Waarde optie 1,Naam optie 2,Waarde optie 2,Reference Txn ID,Factuurnummer,Custom Number,Hoeveelheid,Ontvangstbewijsreferentie,Saldo,Adresregel 1,Adresregel 2/regio/omgeving,Plaats,Staat/Provincie/Regio/Gebied,Zip/Postal Code,Land,Telefoonnummer contactpersoon,Onderwerp,Note,Landcode,Effect op saldo
06-12-2017,17:47:00,CEST,Pietje Puk,Express Checkout betaling,Voltooid,EUR,"100,00","-5,00","95,00",p.puk@sesamstraat.nl,iniminie@sesamstraat.nl,1A207897G9979282J,"Pietje Puk, sesamstraat 1234, Hilversum, 1234AB, NL",Bevestigd,,,"0,00",,"0,00",,,,,,papa 8344,,1,,"1.875,88",sesamstraat 1234,,Hilversum,Noord Holland,1234AB,Nederland,,,,NL,Bij
""")

        converter = PaypalExactTask(('pietje_puk', 'mijn_password'), config, None)
        xml = generateExactTransactionsFile(converter.detailsGenerator(f))

        with open('output.xml', 'w') as f:
            f.write(xml)

        p = os.path.dirname(__file__)
        ref_xml = open(p+'/test.xml', encoding='utf-8-sig').read()

        self.assertEqual(xml, ref_xml)


    def testAllCases(self):
        """ The following cases are tested:
                1. Sale inside the EU
                2. Withdrawl in two stages (with a memo transaction)
                3. Purchase outside the EU
                4. Refunding an earlier sale in the NL (two transactions)
        """
        f = StringIO("""Datum,Tijd,Tijdzone,Naam,Type,Status,Valuta,Bruto,Fee,Net,Van e-mailadres,Naar e-mailadres,Transactiereferentie,Verzendadres,Status adres,Item Title,Objectreferentie,Verzendkosten,Verzekeringsbedrag,Sales Tax,Naam optie 1,Waarde optie 1,Naam optie 2,Waarde optie 2,Reference Txn ID,Factuurnummer,Custom Number,Hoeveelheid,Ontvangstbewijsreferentie,Saldo,Adresregel 1,Adresregel 2/regio/omgeving,Plaats,Staat/Provincie/Regio/Gebied,Zip/Postal Code,Land,Telefoonnummer contactpersoon,Onderwerp,Note,Landcode,Effect op saldo,
6-12-2017,14:09:52,CEST,,Algemeen valutaomrekening,Voltooid,EUR,"95,00","0,00","95,00",iniminie@sesamstraat.nl,,4PE30277P4894911V,,,,,,,,,,,,1A207897G9979282J,,,,,"1.842,05",,,,,,,,,,,Af
6-12-2017,14:09:52,CEST,,Algemeen valutaomrekening,Voltooid,USD,"-117,29","0,00","-117,29",,iniminie@sesamstraat.nl,3XW92795LB086915D,,,,,,,,,,,,1A207897G9979282J,,,,,"677,15",,,,,,,,,,,Bij
6-12-2017,14:09:52,CEST,Pietje Puk,Algemene betaling,Voltooid,USD,"123,46","-6,17","117,29",iniminie@sesamstraat.nl,p.puk@sesamstraat.nl,1A207897G9979282J,"Pietje Puk, sesamstraat 1234, Hilversum, 1234AB, DK",Niet-bevestigd,,,,,,,,,,,papa 8344,,,,"0,00",,,,,,,,,,DK,Af
2-12-2017,09:45:19,CEST,,Algemene opname,In behandeling,EUR,"-1.940,00","0,00","-1.940,00",iniminie@sesamstraat.nl,,2L588208NH679605T,,,,,,,,,,,,,,,,,"2,34",,,,,,,,,,,Af
2-12-2017,10:01:15,CEST,,Algemene opname,Voltooid,EUR,"-1.940,00","0,00","-1.940,00",iniminie@sesamstraat.nl,,2L588208NH679605T,,,,,,,,,,,,,,,,,"2,34",,,,,,,,,,,Memo
6-12-2017,14:09:52,CEST,,Algemeen valutaomrekening,Voltooid,EUR,"-659,76","0,00","-659,76",iniminie@sesamstraat.nl,,4PE30277P4894911V,,,,,,,,,,,,6A756367J4927764X,,,,,"1.842,05",,,,,,,,,,,Af
6-12-2017,14:09:52,CEST,,Algemeen valutaomrekening,Voltooid,USD,"677,15","0,00","677,15",,iniminie@sesamstraat.nl,3XW92795LB086915D,,,,,,,,,,,,6A756367J4927764X,,,,,"677,15",,,,,,,,,,,Bij
6-12-2017,14:09:52,CEST,Pietje Puk,Algemene betaling,Voltooid,USD,"-677,15","0,00","-677,15",iniminie@sesamstraat.nl,p.puk@sesamstraat.nl,6A756367J4927764X,"Pietje Puk, sesamstraat 1234, Hilversum, 1234AB, NL",Niet-bevestigd,,,,,,,,,,,,,,,"0,00",,,,,,,,,,,Af
2-12-2017,05:23:35,CEST,Pietje Puk,Express Checkout betaling,Voltooid,EUR,"160,40","-5,48","154,92",p.puk@sesamstraat.nl,iniminie@sesamstraat.nl,94Y71337XM919902F,"Pietje Puk, sesamstraat 1234, Hilversum, 1234AB, NL",Bevestigd,,,"0,00",,"0,00",,,,,,papa 9293,,1,,"1.331,90",sesamstraat 1234,,Hilversum,Noord Holland,1234AB,Nederland,,,,NL,Bij
30-12-2017,01:33:18,CEST,Pietje Puk,Terugbetaling,Voltooid,EUR,"-128,45","4,11","-124,34",iniminie@sesamstraat.nl,p.puk@sesamstraat.nl,97R07110EC540663X,"Pietje Puk, sesamstraat 1234, Hilversum, 1234AB, NL",Niet-bevestigd,,,"0,00",,"0,00",,,,,94Y71337XM919902F,papa 9293,,,,"391,25",,,,,,,,,,,Af
""")
        converter = PaypalExactTask(('pietje_puk', 'mijn_password'), config, None)
        xml = generateExactTransactionsFile(converter.detailsGenerator(f))

        with open('output.xml', 'w') as f:
            f.write(xml)


    def testRealFile(self):
        # Test converting a real file.
        fname = os.path.join('/home/ehwaal/tmp/pp_retro_q1-3.csv')
        converter = PaypalExactTask(('pietje_puk', 'mijn_password'), config, None)
        xml = generateExactTransactionsFile(converter.detailsGenerator(fname))
        with open('/home/ehwaal/tmp/pp_retro_q1-3.xml', 'w') as f:
            f.write(xml)

    def testEnglishLanguage(self):
        fname = 'pp_testdata2.csv'
        converter = PaypalExactTask(('pietje_puk', 'mijn_password'), config, None)
        xml = generateExactTransactionsFile(converter.detailsGenerator(fname))

    def testWithZekeData(self):
        details = zeke.ZekeDetails(username='pietje', url='http://pietje_puk.com')

        with sessionScope():
            _account = zeke.ZekeAccount(**asdict(details))

        zeke.readTransactions(['export_icp_01-01-2017_02-10-2017.csv',
                               'export_invoices_01-01-2017_02-10-2017.csv'], details)

        # Check that the ICp transactions were properly found
        icp = [8472, 8496, 8594, 8595, 8697, 8695, 9023, 9105, 9079, 9159, 9174, 9384, 9449, 9559,
               10845, 11415, 11589, 11660]
        with sessionScope():
            for t in zeke.ZekeTransaction.select(lambda t: True):
                self.assertEqual(t.btwcode is not None, t.order_nr in icp)
                region = zeke.classifySale(t.order_nr)
                if t.order_nr in icp:
                    self.assertEqual(zeke.classifySale(t.order_nr), SalesType.EU_ICP)
                else:
                    self.assertNotEqual(region, SalesType.EU_ICP)
                    self.assertNotEqual(region, SalesType.Unknown)

        ignore = ['8315', '8451', '7918', '0000706854522914', '27292918474', '9506', '27292554504', '9506', '9506', '10001', '10001', '28169824223', '11012', '11012', '11029', '11029', '11169', '11169', '11531', '11531', '17091205', '17091205', '17091205', '17091205', '17091205', '7918', '0000706854522914', '27292918474', '9506', '27292554504', '9506', '9506', '10001', '10001', '28169824223', '11012', '11012', '11029', '11029', '11169', '11169', '11531', '11531', '17091205', '17091205', '17091205', '17091205', '17091205']


        def test_classifier(transaction: PPTransactionDetails):
            region = zeke_classifier(transaction)
            match = order_nr_re.match(transaction.Factuurnummer)
            if match:
                # For some reason, there is no info on several transactions
                if match.groups()[0] not in ignore:
                    self.assertNotEqual(region, SalesType.Unknown)
            return region

        # Now process the paypal transactions
        fname = os.path.join('pp_testdata.csv')
        converter = PaypalExactTask(('pietje_puk', 'mijn_password'), config, None, zeke_classifier)
        transactions = list(converter.detailsGenerator(fname))
        xml = generateExactTransactionsFile(converter.detailsGenerator(fname))
        with open('pp_testdata.xml', 'w') as f:
            f.write(xml)



if __name__ == '__main__':
    main()
