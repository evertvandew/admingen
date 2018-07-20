#!/usr/bin/env python3


import subprocess
from argparse import ArgumentParser
import time
from admingen.logging import logging
from admingen.keyring import KeyRing


def run():
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

    args = parser.parse_args()

    # Ask for the keyring password and check it is OK.
    pw = input('Please provide the keyring password:')
    _ = KeyRing(args.keyring, pw)

    logging.debug('Opened keyring')

    arguments = ['-k', args.keyring,
                 '-c', args.config,
                 '-l', args.transactionlog] + args.taskids

    period = 24*60*60

    runnext = time.time()

    while True:
        if time.time() < runnext:
            time.sleep(60)
            continue

        # It is time to run the task...
        logging.info('Running periodic task')
        proc = subprocess.Popen(['./run_ppexport.py']+arguments,
                                stdin=subprocess.PIPE)

        # The task needs the password...
        proc.communicate(pw.encode('utf-8'))

        runnext += period

        logging.info('Will run again at %s'%(runnext))


if __name__ == '__main__':
    run()