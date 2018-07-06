#!/usr/bin/env python3
""" Simple script that runs the paypal export and exact import.
    When started, the passport for the keychain must be given on stdin.
    Other details are given as command line options.
"""


from argparse import ArgumentParser
from paypal_exact.worker import PaypalExactTask
from admingen.keyring import KeyRing
from admingen.data import DataReader



if __name__ == '__main__':
    parser = ArgumentParser(description='Runner for the paypal export to Exact Online.'
                                        'This program stores secrets in a keyring file.'
                                        'The password to this keyring is received on stdin.'
                            )
    parser.add_argument('task_id', help='ID for the current task, '
                                        'used to retrieve its configuration',
                        default='1')
    parser.add_argument('-k', '--keyring', help='Path to the keyring file.',
                      default='oauthring.enc')
    parser.add_argument('-d', '--database',
                      help='Url to the database containing the task configuration.'
                           'Defaults to a CSV data file on stdin.',
                      default='stdin')

    args = parser.parse_args()
    task_id = int(args.task_id)

    # Read the keyring password from stdin and open the keyring
    pw = input('Please provide the keyring password:')
    keyring = KeyRing(args.keyring, pw)

    # Read the database and extract the paypal_export_config for the required task_id
    data = DataReader(args.database)
    #index the configuration by task_id
    config = {d.taskid:d for d in data['ExactConfig']}

    details = config[task_id]

    secrets = keyring[args.task_id]
    # The keyring only stores basic Python types.
    # Cast the secrets to the expected complex types.
    secrets_types = PaypalExactTask.__annotations__['secrets']
    secrets = [t(**d) for t, d in zip(secrets_types, secrets)]

    worker = PaypalExactTask(task_id, [details], secrets)
    worker.run()
