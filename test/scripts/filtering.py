
import sys
from admingen.data import filter
from datetime import datetime, timedelta
from decimal import Decimal
from admingen.util import isoweekno2day
from admingen.data import dataline


def script(Klant, Opdracht, WerkerTarief, Uren):
    # The user must supply the period as a command-line argument, using e.g. period=201804
    period = '201804'
    # Also the opdracht must be supplied
    opdracht = 2

    # Calculate the begin and end days of weeks
    for u in Uren:
        u.start = isoweekno2day(int(u.weeknr[:4]), int(u.weeknr[4:]))
        u.eind = u.start + timedelta(6, 0)

    period_start = datetime(int(period[:4]), int(period[4:]), 1)
    period_eind = datetime(int(period[:4]), int(period[4:]) + 1, 1) - timedelta(1, 0)

    uren = [u for u in Uren if not (u.eind < period_start or u.start > period_eind)]
    uren_masks = {u.weeknr: [(period_start <= d < period_eind)
                             for d in [u.start + timedelta(i) for i in range(7)]]
                  for u in uren}

    factuur = dataline()
    o = Opdracht[opdracht]
    factuur.werker = WerkerTarief[o.werker]
    opdracht_uren = [u for u in uren if u.opdracht == o.id]
    _lines = [(u.weeknr, [getattr(u, d, 0) for d in ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo']]) for u
               in opdracht_uren]
    _lines_filtered = [(w, [a * b for a, b in zip(l, uren_masks[w])]) for w, l in _lines]
    weeks = [{'nr': w, 'days': d, 'all': sum(d)} for w, d in _lines_filtered]
    total_uren = Decimal(sum(u for w, l in _lines_filtered for u in l))

    factuur.uren=total_uren
    factuur.netto=total_uren * factuur.werker.tarief
    factuur.btw=Decimal('0.21') * total_uren * factuur.werker.tarief
    factuur.bruto=Decimal('1.21') * total_uren * factuur.werker.tarief
    factuur.datum=datetime.now()
    factuur.nummer = '%s%03i%02i1'%(period_start.year, o.id, period_start.month)
    factuur.opdracht = o
    factuur.periode = period_start
    factuur.weeks = weeks
    o.opdrachtgever = Klant[o.opdrachtgever]

    return factuur


#filter(open('urendata.csv'), script, sys.stdout)
filter(open('urendata.csv'), open('process_factuur').read(), sys.stdout)
