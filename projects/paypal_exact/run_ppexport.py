#!/usr/bin/env python3
""" Simple script that runs the paypal export and exact import.
    When started, the passport for the keychain must be given on stdin.
    Other details are given as command line options.
"""

import sys

from argparse import ArgumentParser
from admingen.keyring import KeyRing
from admingen.data import DataReader
from admingen.logging import logging
from admingen.db_api import openDb
from admingen.clients.exact_xml import testLogin, FileTokenStore, OAuth2

try:
    from paypal_exact.worker import PaypalExactTask
except ModuleNotFoundError:
    import sys
    import os.path
    sys.path.append(os.path.dirname(__file__)+'/..')
    from paypal_exact.worker import PaypalExactTask

from paypal_exact.worker import PaypalExactTask, OAuthDetails, PaypalSecrets, paypal_export_config


if __name__ == '__main__':
    parser = ArgumentParser(description='Runner for the paypal export to Exact Online.'
                                        'This program stores secrets in a keyring file.'
                                        'The password to this keyring is received on stdin.'
                            )
    parser.add_argument('taskids', help='ID(s) for the task(s) to be run.'
                                        'By default, all tasks are run.', nargs='*')
    parser.add_argument('-k', '--keyring', help='Path to the keyring file.',
                      default='oauthring.enc')
    parser.add_argument('-c', '--config',
                      help='Url to the database containing the task configuration.'
                           'Defaults to a CSV data file on stdin.',
                      default='stdin')
    parser.add_argument('-l', '--transactionlog',
                      help='Url to the database containing the transaction log.'
                           'Defaults to "sqlite://transactionlog.db".',
                      default='sqlite://transactionlog.db')
    parser.add_argument('-r', '--range',
                        help='The range for the batch in the form yyyy/mm/ss-yyyy/mm/ss,'
                             ' or one of these strings: today, yesterday, last_month, last_3_months'
                             ' or last_6_months.',
                        default= 'yesterday')
    parser.add_argument('-f', '--file',
                        help='File containing the paypal transactions',
                        default=None)
    parser.add_argument('-t', '--test', help='Perform a test run: don\'t upload to exact.',
                        action='store_true')
    parser.add_argument('--test-exact', help='Only test the login to Exact Online.'
                                             'For example to get an initial OAuth token.',
                        action='store_true')
    args = parser.parse_args()

    # Read the keyring password from stdin and open the keyring
    pw = input('Please provide the keyring password:')
    keyring = KeyRing(args.keyring, pw)

    # Read the database and extract the paypal_export_config for the required task_id
    data = DataReader(args.config)
    #index the configuration by task_id
    taskconfig = {d.taskid:d for d in data['TaskConfig']}
    userconfig = {d.customerid:d for d in data['CustomerConfig']}

    # If no task ids are specified, run all tasks
    taskids = args.taskids or taskconfig.keys()
    taskids = [int(i) for i in taskids]

    if args.test_exact:
        task_details = paypal_export_config(**taskconfig[taskids[0]].__dict__)
        customer_id = task_details.customerid
        customer_details = userconfig[customer_id]
        exact_secrets = keyring['exact_secrets_%s' % customer_id]
        exact_secrets = OAuthDetails(**exact_secrets)
        store = FileTokenStore('exacttoken_%s.json' % customer_id)
        oa = OAuth2(store, exact_secrets)
        t = testLogin(oa)
        print ('OK' if t else 'PROBLEM DURING LOGIN')
        sys.exit(0 if t else 1)

    if args.test:
        args.transactionlog = 'sqlite://:memory:'

    # Connect to the transaction log, generate it if necessary
    openDb(args.transactionlog)

    for task_id in taskids:
        try:
            task_details = paypal_export_config(**taskconfig[task_id].__dict__)
            customer_id = task_details.customerid
            customer_details = userconfig[customer_id]

            pp_secrets = keyring['ppsecrets_%s'%task_id]
            # We assume that the customer uses one exact account for all its clients
            exact_secrets = keyring['exact_secrets_%s'%customer_id]

            # The keyring only stores basic Python types.
            # Cast the secrets to the expected complex types.
            pp_secrets = PaypalSecrets(**pp_secrets)
            exact_secrets = OAuthDetails(**exact_secrets)

            worker = PaypalExactTask(task_id, task_details, exact_secrets, pp_secrets)
            worker.run(period=args.range.upper(), fname=args.file, test=args.test)
        except:
            logging.exception('Failed to run task %s'%task_id)
