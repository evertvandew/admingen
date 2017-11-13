

from datetime import date
from unittest import TestCase
import os, os.path
from pony import orm

from admingen import reporting

TESTDB = 'test.db'

def fillDb(tables):
    with orm.db_session:
        klant =tables['Klant'](naam='Axians')
        opdracht = tables['Opdracht'](naam='DRIS Neckerspoel',
                                     omschrijving='Aanpassingen voor uitrol in station Neckerspoel',
                                     start=date(2017, 10, 1),
                                     end=date(2017, 12, 31),
                                     opdrachtgever=klant)

        werker = tables['Werker'](naam='Evert van de Waal',
                                  standaardtarief=90)
        wt = tables['WerkerTarief'](werker=werker, opdracht=opdracht, tarief=70)

        weken = [tables['Weekstaat'](weeknr=w,
                 jaar=2017) for w in [40, 41, 42, 43]]

        staten = [[0, 0, 8, 0, 7.5, 0, 0],
                  [0, 0, 8, 0, 8, 0, 0],
                  [0, 0, 8, 0, 8, 0, 0],
                  [0, 0, 8, 0, 8, 0, 0]]

        staten = [{d for d in zip(['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo'], staat)} \
                  for staat in staten]

        uren = [tables['Urenregel'](week=week, opdracht=opdracht, werker=werker, **staat)  \
                for week, staat in zip(weken, staten)]


template = """.. header::


        .. image:: logo_vdwi_notext.png
          :height: 1cm
          :align: left

.. footer::

  Wij verzoeken u vriendelijk het verschuldigde bedrag binnnen 30 dagen over te maken
  onder vermelding van het factuurnummer.
  
  Op alle diensten zijn onze algemene voorwaarden van toepassing. 
  Deze kunt u downloaden van onze website.
  
Factuur
===========

.. list-table::
       
        * - Factuurnummer:
          - $factuur.id

        * - Factuurdatum:
          - $factuur.datum
        
        * - Uw referentie:
          - $opdracht.uw_referentie
          
        * - Betreft:
          - $opdracht.naam: $opdracht.omschrijving




.. list-table::
        :widths: 12 10 45 13
        :header-rows: 1
        
        * - Datum
          - id
          - Omschrijving
          - Bedrag

        * - 12-06-2017
          - 17200090
          - R.E.J. VAN GROL EO Tienden
          - €      842,00

        * -
          -
          - **Totaal:**
          - **€      842,00**

"""


class TestReporting(TestCase):
    def setUp(self):
        # Delete the database if there is one left-over
        if False and os.path.exists(TESTDB):
            os.remove(TESTDB)

    def testFactuur(self):
        with open('uren_crm.txt') as f:
            transitions, db, dbmodel = readconfig(f)
        # Instantiate the database
        db.bind(provider='sqlite', filename=TESTDB, create_db=True)
        db.generate_mapping(create_tables=True)
        fillDb(dbmodel)

        # Now generate the factuur
