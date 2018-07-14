#!/usr/bin/env python3
""" Simple script that runs the paypal export and exact import.
    When started, the passport for the keychain must be given on stdin.
    Other details are given as command line options.
"""


from argparse import ArgumentParser
from admingen.keyring import KeyRing
from admingen.data import DataReader
from admingen.logging import logging
from admingen.db_api import openDb

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
    parser.add_argument('-t', '--transactionlog',
                      help='Url to the database containing the transaction log.'
                           'Defaults to "sqlite://transactionlog.db".',
                      default='sqlite://transactionlog.db')
    parser.add_argument('-r', '--range',
                        help='The range for the batch in the form yyyy/mm/ss-yyyy/mm/ss',
                        default= 'yesterday')
    parser.add_argument('-f', '--file',
                        help='File containing the paypal transactions',
                        default=None)
    args = parser.parse_args()

    # Read the keyring password from stdin and open the keyring
    pw = input('Please provide the keyring password:')
    keyring = KeyRing(args.keyring, pw)

    # Connect to the transaction log, generate it if necessary
    openDb(args.transactionlog)


    # Read the database and extract the paypal_export_config for the required task_id
    data = DataReader(args.config)
    #index the configuration by task_id
    taskconfig = {d.taskid:d for d in data['TaskConfig']}
    userconfig = {d.customerid:d for d in data['CustomerConfig']}

    # If no task ids are specified, run all tasks
    taskids = args.taskids or taskconfig.keys()

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
            worker.run(fname=args.file)
        except:
            logging.exception('Failed to run task %s'%task_id)
