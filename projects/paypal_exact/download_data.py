#!/usr/bin/env python3
""" Download data for a specific paypal-exact task """

from argparse import ArgumentParser
import shutil
import datetime
import os
import logging
from admingen.keyring import KeyRing
from admingen.data import DataReader

from admingen.clients.paypal import downloadTransactions, DataRanges, PaypalSecrets



def run(task_ids, keychain, directory):
    for task_id in task_ids:
        try:
            rundir = os.path.join(directory, 'task_%i'%task_id)

            # Extract the paypal login from the central keychain
            key = 'ppsecrets_%i'%task_id
            login = keychain[key]
            pp_login = PaypalSecrets(**login)

            # Download the paypal transactions for yesterday
            fname = downloadTransactions(pp_login, DataRanges.YESTERDAY)

            # Copy the file to the right location
            yesterday = datetime.datetime.today() - datetime.timedelta(1,0)
            dest = yesterday.strftime('paypaldownload_%Y-%m-%d')
            shutil.move(fname, os.path.join(rundir, dest))
        except:
            logging.exception('Error when downloading task %s'%task_id)


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
    parser.add_argument('-d', '--directory', help='Main directory for the downloader. '
                        'This is where the taskconfig.csv file etc lives.',
                        default='/home/ehwaal/tmp/pp_export/test-data')
    args = parser.parse_args()


    pw = input('Please provide the keyring password:')
    keyring = KeyRing(args.keyring, pw)

    taskconfig = DataReader('/home/ehwaal/admingen/projects/paypal_exact/taskconfig.csv')

    if not args.taskids:
        taskids = taskconfig['TaskConfig'].keys()
    else:
        taskids = [int(i) for i in args.taskids]
    for i in taskids:
        if i not in taskconfig['TaskConfig']:
            logging.error('Ignoring unknown task ID %s'%i)
    taskids = [i for i in taskids if i in taskconfig['TaskConfig']]

    run(taskids, keyring, args.directory)
