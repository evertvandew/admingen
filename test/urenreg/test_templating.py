
import datetime
from unittest import TestCase
import calendar
import os, os.path
from decimal import Decimal

from admingen.appengine import readconfig
from admingen.db_api import the_db, orm, sessionScope
from admingen.util import isoweekno2day
from admingen.reporting import render


database = 'test.db'


class Test(TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(database):
            os.remove(database)
        # Load the model and create the database
        with open('uren_crm.txt') as f:
            model = readconfig(f)
        cls.model = model
        # Instantiate the database
        the_db.bind(provider='sqlite', filename=':memory:', create_db=True)
        the_db.generate_mapping(create_tables=True)
        orm.sql_debug(True)

        cls.fillDatabase()

    @classmethod
    def fillDatabase(cls):
        # Create two customers, two projects, and a set of hour sheets.
        Persoon = cls.model.dbmodel['Persoon']
        Werker = cls.model.dbmodel['Werker']
        WerkerTarief = cls.model.dbmodel['WerkerTarief']
        Adres = cls.model.dbmodel['Adres']
        Klant = cls.model.dbmodel['Klant']
        Opdracht = cls.model.dbmodel['Opdracht']
        Urenregel = cls.model.dbmodel['Urenregel']
        Weekstaat = cls.model.dbmodel['Weekstaat']
        Factuur = cls.model.dbmodel['Factuur']
        WeekFactuur = cls.model.dbmodel['WeekFactuur']


        with sessionScope():
            genio = Persoon(naam='Genio van Hoof',
                            email='genio.vanhoof@axians.com')
            ron   = Persoon(naam='Ronald Need',
                            email='rneed@dis-sensors.nl')
            axians = Klant(naam='Axians ICT b.v.',
                           adres=Adres(straat_nummer='Rivium Boulevard 41',
                                       postcode='2909 LK',
                                       plaats='Capelle aan den Ĳssel'),
                           contactpersoon=genio)
            dis = Klant(naam='DIS sensors b.v.',
                        adres=Adres(straat_nummer='Oostergracht 40',
                                    postcode='3763 LZ',
                                    plaats='Soest'),
                        contactpersoon=ron)

            evert = WerkerTarief(werker=Werker(naam='Evert van de Waal',
                                               sofinr='1705.43.304'),
                                 tarief='70')

            neck = Opdracht(naam='DYNNIQ: 43889 NECKERSPOEL',
                            opdrachtgever=axians,
                            werkers=[evert])

            inclino = Opdracht(naam='323 Dynamic Inclino',
                               opdrachtgever=dis,
                               werkers=[evert])

            # Now create some urenregels
            uren_neck = '''201740 0 0 8 0 7.5
                           201741 0 0 8 0 8
                           201742 0 0 8 0 8
                           201743 0 0 8 0 8
                           201744 0 0 8
                           201745 0 0 4
                           201746 0 0 6
                           201748 0 0 8
                           201750 0 0 8
                           201751 0 0 8
                           201802 0 0 8
                           201803 0 0 0 0 8
                           201805 0 0 0 0 8'''

            uren_dis = '''201805 0 0 7 6
                          201806 0 0 8 5.5 8
                          201807 0 0 8 4
                          201808 0 0 8 5'''

            weekstates = {}

            for hrs, opdr in [[uren_neck, neck],
                              [uren_dis, inclino]]:
                for week_hrs in hrs.splitlines():
                    weeknr, *hrs = week_hrs.split()
                    ws = weekstates.get(weeknr, None)
                    ws = ws or Weekstaat(weeknr=int(weeknr[4:]), jaar=int(weeknr[:4]))
                    weekstates[weeknr] = ws

                    # Ensure there are at least 5 days with hours
                    hrs.extend([0, 0, 0, 0, 0])
                    hrs = [float(h) for h in hrs]

                    opdr.uren.add(Urenregel(week=ws,
                                            werker=evert,
                                            ma=hrs[0],
                                            di=hrs[1],
                                             wo=hrs[2],
                                            do=hrs[3],
                                            vr=hrs[4],
                                            za=0.0,
                                            zo=0.0))

            # For each week, determine the correct start and end
            for weeknr, ws in weekstates.items():
                year, week = int(weeknr[:4]), int(weeknr[4:])
                ws.start = isoweekno2day(year, week)
                ws.eind = ws.start + datetime.timedelta(6, 0)

            # Commit the details so far: we need record id's below.
            orm.commit()

            # Generate the factuur objecten (but without accounting details)
            for periods, opdr in [[['201710', '201711', '201712', '201801', '201802'], neck],
                                  [['201801', '201802'], inclino]]:
                for period in periods:
                    p = datetime.datetime.strptime(period, '%Y%m')
                    factnr = '%s%03i%02i1'%(p.year, opdr.id, p.month)
                    opdr.facturen.add(Factuur(werker=evert,
                                              periode=p,
                                              nummer=factnr))


    def testManualFactuur(self):
        # Manually test performing the queries and rendering the template
        Factuur = self.model.dbmodel['Factuur']
        Weekstaat = self.model.dbmodel['Weekstaat']
        with sessionScope():
            facturen = orm.select(f for f in Factuur)[:]
            for factuur in facturen:
                # Process the urenstaten to calculate the facturen
                nr_days = calendar.monthrange(factuur.periode.year, factuur.periode.month)[1]
                start = factuur.periode
                end = start + datetime.timedelta(nr_days, 0)
                _weeks = orm.select(w for w in Weekstaat if (w.start + datetime.timedelta(4)) >= start and w.start < end)[:]
                _week_filter = {w.weeknr: [(start <= d < end)
                                       for d in [w.start + datetime.timedelta(i) for i in range(7)]]
                                for w in _weeks}
                _lines = [(w.weeknr, l) for w in _weeks for l in w.uren if
                         l.werker == factuur.werker and l.opdracht == factuur.opdracht]
                _lines2 = [(w, [getattr(l, d) for d in ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo']]) for w, l
                          in _lines]
                _lines_filtered = [(w, [a * b for a, b in zip(l, _week_filter[w])]) for w, l in _lines2]
                weeks = [{'nr': w, 'days': d, 'all': sum(d)} for w, d in _lines_filtered]
                total_uren = Decimal(sum(u for w, l in _lines_filtered for u in l))

                factuur.set(uren=total_uren,
                            netto=total_uren*factuur.werker.tarief,
                            btw=Decimal('0.21')*total_uren*factuur.werker.tarief,
                            bruto=Decimal('1.21') * total_uren * factuur.werker.tarief,
                            datum=datetime.datetime.now())

                # Render the template
                with open('../templates/factuur.fodt') as f:
                    templ = f.read()

                render(templ,
                       '%s.fodt' % factuur.nummer,
                       weeks=weeks,
                       total_uren=total_uren,
                       factuur=factuur,
                       werker=factuur.werker.werker
                       )

    def testFactuur(self):
        # Try to get the factuur details 'view' from the database.
        pass

    def testUrenstaat(self):
        # Get an urenregel
        Urenregel = self.model.dbmodel['Urenregel']
        with sessionScope():
            regel = orm.select(u for u in Urenregel if u.week.weeknr==8).first()
            with open('../templates/dynniq-weekstaat.fods') as f:
                templ = f.read()

            render(templ,
                   'test.fods',
                   'xls',
                   staat=regel,
                   total=sum([regel.ma, regel.di, regel.wo, regel.do, regel.vr, regel.za, regel.zo])
                   )

            with open('../templates/dis-weekstaat.fods') as f:
                templ = f.read()

            render(templ,
                   'test1.fods',
                   'xls',
                   staat=regel,
                   total=sum([regel.ma, regel.di, regel.wo, regel.do, regel.vr, regel.za, regel.zo])
                   )
