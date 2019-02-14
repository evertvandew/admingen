"""
Compare with old uploads using:
set filter="(Rate)|(GLTransactionLine)|(Transactie)"; diff -bB <(egrep -v "$filter" ~/admingen/projects/paypal_exact/test.xml) <(egrep -v "$filter" pp_export/test-data/task_1/upload2018.xml) | less
"""
from decimal import Decimal
import subprocess
import argparse
import xml.etree.ElementTree as ET
import os, os.path


from admingen.data import DataReader
from admingen.clients.paypal import pp_reader
from paypal_converter import (paypal_export_config, SalesType, group_currency_conversions,
                              classifiers)


def run(configpath, basedir, taskid, ofname):
    # Read the configuration
    data = DataReader(configpath)
    config = paypal_export_config(**data['TaskConfig'][taskid])
    home = os.path.join(basedir, 'task_%s'%taskid)
    fname = home + '/Download.CSV'

    ###############################################################################
    # Check the output file: esp. the effect on saldo for the pp_account.

    # Run a subprocess that executes a XPATH query to determine the effect on saldo.
    if config.currency == 'EUR':
        cmnd = '''xmlstarlet sel -t -v "sum(//GLTransactionLine[GLAccount[@code=%s]]/Amount/Value)" %s'''
    else:
        cmnd = '''xmlstarlet sel -t -v "sum(//GLTransactionLine[GLAccount[@code=%s]]/ForeignAmount/Value)" %s'''
    cmnd = cmnd % (config.pp_account, ofname)
    p = subprocess.Popen(cmnd, shell=True, stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    d_saldo = Decimal(int(float(stdout)*100 + 0.5)) / 100

    transactions = list(pp_reader(fname))
    start = [t for t in transactions if t.Valuta == config.currency][0]
    end = [t for t in reversed(transactions) if t.Valuta == config.currency][0]

    start_saldo = start.Saldo - start.Net
    end_saldo = end.Saldo
    msg = 'Error in saldo: expected %s actual %s'%(end_saldo-start_saldo, d_saldo)
    assert end_saldo - start_saldo == d_saldo, msg



if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('-c', '--config', default='/home/ehwaal/admingen/projects/paypal_exact/taskconfig.csv')
    p.add_argument('-b', '--basedir', default='/home/ehwaal/tmp/pp_export/test-data/')
    p.add_argument('-t', '--taskid', default=1)
    p.add_argument('-o', '--outfile', default='test2.xml')
    args = p.parse_args()
    run(args.config, args.basedir, args.taskid, args.outfile)
