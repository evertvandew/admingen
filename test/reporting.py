

from datetime import date, datetime, timedelta
from unittest import TestCase
import os, os.path
from pony import orm
from jinja2 import FileSystemLoader, Environment, Template
import google_calendar
from decimal import Decimal, ROUND_HALF_UP
from babel.numbers import format_currency

from admingen.dbengine import readconfig
from admingen.db_api import sessionScope, select, the_db
from admingen.util import EmptyClass

TESTDB = 'test.db'


def moneyformat(input):
    return format_currency(input, 'EUR', locale='nl_NL.utf8')

env = Environment(autoescape=True)

env.filters['moneyformat'] = moneyformat

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
                                  sofinr='1234.567.89',
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
                 eind=week1+timedelta(7*w)) for w in [39, 40, 41, 42, 43, 44, 45]]

        staten = [[6, 7, 1, 1, 1],
                  [0, 0, 8, 0, 7.5],
                  [0, 0, 8, 0, 8],
                  [0, 0, 8, 0, 8],
                  [0, 0, 8, 0, 8],
                  [5, 6, 7, 8, 0],
                  [1, 2, 3, 4, 5]]

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
        nr_days = google_calendar.monthrange(year, month)[1]
        start = datetime.strptime('01-%s-%s'%(month, year), '%d-%m-%Y')
        end = start + timedelta(nr_days, 0)

        def day_list(regel):
            return [getattr(regel, i) for i in ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo']]

        with sessionScope():
            # Get the weekstaten that are relevant
            opdracht = select(o for o in Opdracht).first()
            weeks = list(select(w for w in Weekstaat if (w.start+timedelta(4)) >= start and w.start < end))

            data = EmptyClass()
            data.naam = opdracht.opdrachtgever.naam
            data.contactpersoon = opdracht.opdrachtgever.contactpersoon.naam
            data.adres = opdracht.opdrachtgever.adres

            werkertarief = list(opdracht.werkers)[0]

            weeks = select(w for w in Weekstaat if (w.start + timedelta(4)) >= start and w.start < end)[:]
            week_filter = {w.weeknr:[1.0 if (start <= d < end) else 0.0 for d in [w.start + timedelta(i) for i in range(7)]] for w in weeks}
            lines = [(w.weeknr, l) for w in weeks for l in w.uren
                                if l.werker == werkertarief and l.opdracht == opdracht]
            lines2 = [(w, [getattr(l, d) for d in ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo']]) for
                     w, l in lines]
            lines_filtered = [(w, [a * b for a, b in zip(l, week_filter[w])]) for w, l in lines2]
            weeks = [{'nr': w, 'days': d, 'all': sum(d)} for w, d in lines_filtered]
            all_hours = sum(u for w, l in lines_filtered for u in l)

            data.weeks = weeks

            # Determine how many facturen have been created for this customer
            fact_count = select(f for f in Factuur
                    if f.periode==start and f.opdracht.opdrachtgever == opdracht.opdrachtgever).count()
            factuurnr = '%4i%03i%02i%i'%(start.year, opdracht.opdrachtgever.id, start.month, fact_count+1)
            netto = Decimal(all_hours*float(werkertarief.tarief)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            tax = (netto * Decimal('0.21')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            bruto = netto + tax
            # Create the factuur record
            factuur = Factuur(uren=all_hours,
                              netto=netto,
                              btw=tax,
                              bruto=bruto,
                              opdracht=opdracht,
                              periode=start,
                              nummer=factuurnr,
                              datum=datetime.now())

            data.factuur = factuur
            data.factuurperiode = start.strftime('%b %Y')
            data.werker = werkertarief.werker


            # Now generate the factuur
            with open('templates/factuur.fodt') as f:
                t = env.from_string(f.read())
            s = t.render(data.__dict__)
        with open('%s-%s.fodt'%(factuurnr, opdracht.omschrijving), 'w') as f:
            f.write(s)
