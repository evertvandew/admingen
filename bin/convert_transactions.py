#!/usr/bin/env python3

import sys
import datetime
from argparse import ArgumentParser
from admingen.data import DataReader
from admingen.logging import logging, log_exceptions
from admingen.db_api import openDb, sessionScope

try:
    from paypal_exact.worker import PaypalExactTask
except ModuleNotFoundError:
    import sys
    import os.path
    sys.path.append(os.path.dirname(__file__)+'/..')
    from paypal_exact.worker import PaypalExactTask

from paypal_exact.worker import PaypalExactConverter, PaypalExchangeBatch, paypal_export_config


@log_exceptions
def run():
    parser = ArgumentParser(description='Simple runner that reads a transaction log from Paypal'
                                        'and converts it into a list of Exact transactions.'
                            )
    parser.add_argument('taskid', help='ID for the task being run.')
    parser.add_argument('-c', '--config',
                        help='Url to the database containing the task configuration.'
                             'Defaults to a CSV data file on stdin.',
                        default='stdin')
    parser.add_argument('-f', '--file',
                        help='File containing the paypal transactions',
                        default=None)
    parser.add_argument('-o', '--outfile',
                        help='File to which the XML transactions are written. Default: stdout',
                        default=sys.stdout)
    args = parser.parse_args()

    data = DataReader(args.config)

    # index the configuration by task_id
    taskconfig = {d.taskid: d for d in data['TaskConfig']}
    userconfig = {d.customerid: d for d in data['CustomerConfig']}

    taskid = int(args.taskid)
    task_details = paypal_export_config(**taskconfig[taskid].__dict__)

    openDb('sqlite://:memory:')

    timestamp = datetime.datetime.now()
    with  sessionScope():
        batch = PaypalExchangeBatch(task_id=taskid,
                                    timestamp=timestamp,
                                    period_start=timestamp,
                                    period_end=timestamp)

        worker = PaypalExactConverter(task_details)
        transactions, xml = worker.convertTransactions(args.file, batch)

    sys.stdout.write(xml)



if __name__ == '__main__':
    run()