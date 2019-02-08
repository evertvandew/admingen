from jinja2 import Environment, FileSystemLoader, select_autoescape
from decimal import Decimal
import subprocess
import sys
from admingen.clients.paypal import pp_reader
from admingen.data import DataReader, dataset
from paypal_converter import (paypal_export_config, pp_reader, SalesType, group_currency_conversions,
                              classifiers)

taskid = 3
home = '/home/ehwaal/tmp/pp_export/test-data/task_%i'%taskid
vat_name = home+'/VATs_1.xml'
fname = home+'/Download.CSV'

data = DataReader('/home/ehwaal/admingen/projects/paypal_exact/taskconfig.csv')
config = data['TaskConfig'][taskid]

transactions = dataset(group_currency_conversions(pp_reader(fname), config)) \


transactions = [t for t in transactions if t.Valuta == 'EUR']
for t in transactions:
    t.vatpercent = 0
    t.template = 'LineTemplate'
    t.glaccount = '8100'

env = Environment(loader=FileSystemLoader('.'),
                  autoescape=select_autoescape(['xml']),
                  line_statement_prefix='%',
                  line_comment_prefix='%%')

env.globals.update(abs=abs, Decimal=Decimal, getattr=getattr)

template = env.get_template('exacttransactions.jinja')
sys.stdout.write(template.render(transactions=[transactions], config=config))
ofname = 'test.xml'
with open(ofname, 'w') as out:
    out.write(template.render(transactions=[transactions], config=config))



###############################################################################
# Check the output file: esp. the effect on saldo for the pp_account.

# Run a subprocess that executes a XPATH query to determine the effect on saldo.
cmnd = '''xmlstarlet sel -t -v "sum(//GLTransactionLine[GLAccount[@code=%s]]/Amount/Value)" %s'''
cmnd = cmnd % (config.pp_account, ofname)
p = subprocess.Popen(cmnd, shell=True, stdout=subprocess.PIPE)
stdout, stderr = p.communicate()
d_saldo = Decimal(int(float(stdout)*100 + 0.5)) / 100
print(stdout)
print(stderr)

transactions = list(pp_reader(fname))
start = [t for t in transactions if t.Valuta == config.currency][0]
end = [t for t in reversed(transactions) if t.Valuta == config.currency][0]

start_saldo = start.Saldo - start.Net
end_saldo = end.Saldo
assert end_saldo - start_saldo == d_saldo
print('SUCCES!')