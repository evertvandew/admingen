

from datetime import date, datetime, timedelta
from unittest import TestCase
import os, os.path
from pony import orm
from jinja2 import Template
import calendar

from admingen.dbengine import readconfig
from admingen.db_api import sessionScope, select, the_db
from admingen.util import EmptyClass

TESTDB = 'test.db'

def fillDb(tables):
    with sessionScope():
        cp = tables['Persoon'](naam='Genio van Hoof')
        adr = tables['Adres'](straat_nummer='Rivium boulevard 41',
                              postcode='2909 LK',
                              plaats='Capelle a/d Ĳssel',
                              land='Nederland')
        klant =tables['Klant'](naam='Axians', contactpersoon=cp, adres=adr)
        opdracht = tables['Opdracht'](naam='DRIS Neckerspoel',
                                     omschrijving='Aanpassingen voor uitrol in station Neckerspoel',
                                     ref = '43889',
                                     start=date(2017, 10, 1),
                                     end=date(2017, 12, 31),
                                     opdrachtgever=klant)

        werker = tables['Werker'](naam='Evert van de Waal',
                                  standaardtarief=90)
        wt = tables['WerkerTarief'](werker=werker, opdracht=opdracht, tarief=70)

        week1 = datetime(2017, 1, 1)
        wd = week1.weekday()
        if (wd > 3):
            week1 = week1 + timedelta(7 - wd)
        else:
            week1 = week1 - timedelta(wd)

        weken = [tables['Weekstaat'](weeknr=w,
                 jaar=2017,
                 start=week1+timedelta(7*(w-1)),
                 eind=week1+timedelta(7*w)) for w in [39, 40, 41, 42, 43, 44]]

        staten = [[6, 7, 0, 0, 0],
                  [0, 0, 8, 0, 7.5],
                  [0, 0, 8, 0, 8],
                  [0, 0, 8, 0, 8],
                  [0, 0, 8, 0, 8],
                  [5, 6, 7, 8, 0]]

        staten = [dict(zip(['ma', 'di', 'wo', 'do', 'vr'], staat)) \
                  for staat in staten]

        uren = [tables['Urenregel'](week=week, opdracht=opdracht, werker=wt, **staat)  \
                for week, staat in zip(weken, staten)]


class TestReporting(TestCase):
    def testFactuur(self):
        with open('admingen_tests/uren_crm.txt') as f:
            transitions, db, dbmodel = readconfig(f)

        # Instantiate the database
        the_db.bind(provider='sqlite', filename=":memory:", create_db=True)
        the_db.generate_mapping(create_tables=True)
        fillDb(dbmodel)

        Opdracht = dbmodel['Opdracht']
        Weekstaat = dbmodel['Weekstaat']
        Factuur = dbmodel['Factuur']

        # Perform the queries to get the data for the template.
        month = 10
        year = 2017
        nr_days = calendar.monthrange(year, month)[1]
        start = datetime.strptime('01-%s-%s'%(month, year), '%d-%m-%Y')
        end = start + timedelta(nr_days, 0)

        def day_list(regel):
            return [getattr(regel, i) for i in ['zo', 'ma', 'di', 'wo', 'do', 'vr', 'za']]

        with sessionScope():
            # Get the weekstaten that are relevant
            opdracht = select(o for o in Opdracht).first()
            weeks = list(select(w for w in Weekstaat if w.eind >= start and w.start < end))

            data = EmptyClass()
            data.naam = opdracht.opdrachtgever.naam
            data.contactpersoon = opdracht.opdrachtgever.contactpersoon.naam
            data.adres = opdracht.opdrachtgever.adres

            werkertarief = list(opdracht.werkers)[0]

            data.weeks = []

            all_hours = 0.0

            for week in weeks:
                days = [week.start + timedelta(i, 0) for i in range(7)]
                for line in week.uren:
                    all_week = 0.0
                    if line.opdracht != opdracht or line.werker != werkertarief:
                        continue
                    values = day_list(line)
                    days_filtered = [v if d>= start and d < end else 0.0 for d, v in zip(days, values)]
                    all_week += sum(days_filtered)
                    weekdata = EmptyClass()
                    weekdata.days = days_filtered
                    weekdata.all = all_week
                    all_hours += all_week
                    weekdata.nr = week.start.isocalendar()[1]
                    data.weeks.append(weekdata)

            # Determine how many facturen have been created for this customer
            fact_count = select(f for f in Factuur
                    if f.periode==start and f.opdracht.opdrachtgever == opdracht.opdrachtgever).count()
            factuurnr = '%4i%03i%02i%i'%(start.year, opdracht.opdrachtgever.id, start.month, fact_count+1)
            netto = all_hours*float(werkertarief.tarief)
            # Create the factuur record
            factuur = Factuur(uren=all_hours,
                              netto=netto,
                              btw=netto*0.21,
                              bruto=netto*1.21,
                              opdracht=opdracht,
                              periode=start,
                              nummer=factuurnr,
                              datum=datetime.now())

            data.factuur = factuur
            data.factuurperiode = start.strftime('%b %Y')
            data.werker = werkertarief.werker


        # Now generate the factuur
        with open('templates/factuur.fodt') as f:
            t = Template(f.read())
        s = t.render(data.__dict__)
        with open('%s-%s.fodt'%(factuurnr, opdracht.omschrijving), 'w') as f:
            f.write(s)
