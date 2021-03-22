import json
import operator
import codecs
from decimal import Decimal
import string
import subprocess
import os, os.path
import sys
import re
import datetime
import shutil
import hashlib

binfile = 'rst2pdf.exe' if 'win' in sys.platform else 'rst2pdf'
RST2PDF = shutil.which(binfile)
assert RST2PDF, 'Could not find an executable for rst2pdf, please do sudo apt install rst2pdf'

TRANSACTION_FILE = 'FinTransactionSearch.csv'
PDF_DIR = '{}/{}.all'

REMOVE_PUNC = {ord(char): None for char in string.punctuation}
REMOVE_PUNC[ord(u' ')] = u'_'
REMOVE_PUNC = str.maketrans(REMOVE_PUNC)

UK_2_EU = t = str.maketrans({',': '.', '.': ','})

vardir = os.environ.get('OPSDIR', os.getcwd())


def datesKey(record):
    ''' Get a transaction. Extract the data dates in the form dd-mm-yy or d-m-yy.
        Then return a key that can be sorted directly, i.e. in the form yy-mm-dd.
    '''
    d = record['EntryDate']
    day, month, year = [int(p) for p in d.split('-')]
    return day + 100 * month + 10000 * year


datescanner = re.compile('/Date\(([0-9]*)\)/')

overview_start = string.Template('''Giften overzicht $jaar: $naam
=======================================================================================

Relatienr: $relatie

''')

account_header = '''
%s
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

'''

section_start = '''
.. list-table::
        :widths: 12 10 45 13
        :header-rows: 1

        * - Datum
          - id
          - Omschrijving
          - Bedrag
'''

summary_start = '''
.. list-table::
        :widths: 12 45 13
        :header-rows: 1

        * - Grootboek
          - Omschrijving
          - Bedrag
'''

section_end = string.Template('''        * -
          -
          - **Totaal:**
          - **$totaal**

''')

regel = string.Template('''        * - $datum
          - $boeking
          - $omschrijving
          - $bedrag
''')

summary_line = '''        * - %(code)s
          - %(omschrijving)s
          - %(bedrag)s
'''


def amount2Str(a):
    return '€{:>12,.2f}'.format(a).translate(UK_2_EU)


def odataDate2Datetime(transaction):
    ds = transaction['Date']
    m = datescanner.match(ds)
    if m:
        ms = int(m.groups()[0])
        dt = datetime.datetime.fromtimestamp(ms / 1000.0)
        transaction['Date'] = dt
    return transaction


def generateRstConsolidated(org, relnr, name, gifts, total):
    logo_path = os.environ.get('PROJDIR', '') + '/public/static/' + org['logo']
    yield org['template'] % {'logo': logo_path}
    section_details = dict(jaar=gifts[0]['Date'].year,
                           naam=name,
                           relatie=relnr.strip())
    yield overview_start.substitute(section_details)
    yield section_start
    for gift in gifts:
        amount = amount2Str(-gift['AmountDC'])
        details = dict(datum=gift['Date'].strftime('%d-%m-%Y'),
                       boeking=gift['EntryNumber'],
                       omschrijving=gift['Description'],
                       bedrag=amount)
        yield regel.substitute(details)
    yield section_end.substitute({'totaal': amount2Str(total)})


def generateRstDetailed(org, relnr, name, gifts, total):
    logo_path = 'public/static/' + org['logo']
    yield org['template'] % {'logo': logo_path}
    giver_details = dict(jaar=org['period_start'].year,
                         naam=name,
                         relatie=relnr.strip())
    yield overview_start.substitute(giver_details)
    used_accounts = sorted(gifts.keys())
    subtotals = {}
    for acc in used_accounts:
        acc_descr = org['account_descriptions'][acc]
        yield account_header % acc_descr
        yield section_start
        subtotal = -sum(g['AmountDC'] for g in gifts[acc])
        subtotals[acc] = subtotal
        for gift in gifts[acc]:
            amount = amount2Str(-gift['AmountDC'])
            details = dict(datum=gift['Date'].strftime('%d-%m-%Y'),
                           boeking=gift['EntryNumber'],
                           omschrijving=gift['Description'],
                           bedrag=amount)
            yield regel.substitute(details)
        yield section_end.substitute({'totaal': amount2Str(subtotal)})
    yield account_header % 'Samenvatting'
    yield summary_start
    for acc in used_accounts:
        details = dict(code=acc, omschrijving=org['account_descriptions'][acc],
                       bedrag=amount2Str(subtotals[acc]))
        yield summary_line % details
    yield summary_line % {'code': '', 'omschrijving': '**Totaal:**',
                          'bedrag': '**%s**' % amount2Str(total)}


def generate_overview(org, rel_nr, user, gifts):
    filtered = [g for g in gifts if g['AccountCode'] == rel_nr]
    filtered = sorted(filtered, key=lambda g: g['Date'])
    amounts = [g['AmountDC'] for g in filtered]
    total = -sum(amounts)
    if org['consolidated']:
        rst = '\n'.join(
            r for r in generateRstConsolidated(org, rel_nr, user['Name'], filtered, total))
    else:
        groups = {}
        for t in filtered:
            # The transactions are filtered by date. Now distribute them according to account.
            a = groups.setdefault(t['GLAccountCode'], [])
            a.append(t)
        rst = '\n'.join(r for r in generateRstDetailed(org, rel_nr, user['Name'], groups, total))
    return filtered, total, rst


def parse_accounts(s):
    """ Parse the gift accounts, including ranges. """
    # Remove any spaces around dashes.
    s = s.replace(' -', '-').replace('- ', '-')
    accounts = [acc.strip() for acc in s.split()]
    # Generate the actual result, by expanding the ranges.
    result = []
    for acc in accounts:
        if '-' in acc:
            start, end = [int(a) for a in acc.split('-')]
            result.extend(str(i) for i in range(start, end+1))
        else:
            result.append(acc)
    return result


def generate_overviews(org, users, transactions):
    if not transactions:
        logging.error("NO TRANSACTIONS!")
    gift_accounts = parse_accounts(org['gift_accounts'])
    if not gift_accounts:
        logging.error("NO GIFT ACCOUNTS!")
    gifts = [odataDate2Datetime(t) for t in transactions if t['GLAccountCode'] in gift_accounts]
    users_lu = {u['Code']: u for u in users}
    relatienrs = set(g['AccountCode'] for g in gifts if 'AccountCode' in g and g['AccountCode'])

    for r in relatienrs:
        user = users_lu[r]
        filtered, total, rst = generate_overview(org, r, user, gifts)
        if total:
            yield (r, user['Name'], user['Email'], total, rst)


def pdfName(org_id, user_name, user_code):
    salt = b'EenGedrukte,Geschudde,OverlopendeMaat'

    upart = (user_name.translate(REMOVE_PUNC) + '_%s' % user_code.strip('_ ')).encode('utf8')
    m = hashlib.sha1()
    m.update(salt)
    m.update(upart)
    if org_id:
        return os.path.join(PDF_DIR.format(vardir, org_id),
                            m.hexdigest() + '.pdf')
    else:
        return m.hexdigest() + '.pdf'

def pdfUrl(user_name, user_code):
    path = pdfName(None, user_name, user_code)
    return os.path.join('/all/' + path)

def pdfUrl2Name(org_id, pdfurl):
    # If we have a full path, we only need the final part.
    if '/' in pdfurl:
        pdfurl = '/'.split(pdfurl)[-1]
    return os.path.join(PDF_DIR.format(vardir, org_id), pdfurl)

def generate_pdfs(org, users, transactions, status_update=None):
    temp_file = '%i.temp.rst' % org['id']
    pdfdir = PDF_DIR.format(vardir, org['id'])
    if not os.path.exists(pdfdir):
        os.mkdir(pdfdir)
    for code, name, email, total, rst in generate_overviews(org, users, transactions):
        with open(temp_file, 'w') as f:
            f.write(rst)
        fname = pdfName(org['id'], name, code)
        cmnd = [RST2PDF, temp_file, '-o', fname, '-s', 'stylesheet.txt']
        if status_update:
            status_update(name)
        subprocess.call(cmnd)


if __name__ == '__main__':
    users = json.loads(open('users.json').read())
    transactions = json.loads(open('transactions.json').read(), parse_float=Decimal)
    # user = [u for u in users if u['Code'].strip() == '1661']
    # gifts = [odataDate2Datetime(t) for t in transactions if t['GLAccountCode'] in gift_accounts]
    # generate_overview('              1661', user[0], gifts)
    generate_pdfs(users, transactions)


# To generate a PDF run: c:\Python26\Scripts\rst2pdf.exe overzichten.rst -o overzichten.pdf -s stylesheet.txt

