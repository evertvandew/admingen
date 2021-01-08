#!/usr/bin/env python3

import json
import sys
import os
import os.path
from decimal import Decimal

from admingen.project_runner import set_context


USERS_FILE = '{}/{}.users.json'
TRANSACTIONS_FILE = '{}/{}.transactions.json'
ACCOUNTS_FILE = '{}/{}.accounts.json'


def getDefaultOrg():
    with model.sessionScope():
        organisations = [o for o in model.Organisation.select()]
        if len(organisations) == 1:
            return organisations[0].to_dict(with_lazy=True)

def run(org):
    org_id = org['id']
    transactions = json.loads(open(TRANSACTIONS_FILE.format(config.opsdir, org_id)).read(), parse_float=Decimal)
    users = json.loads(open(USERS_FILE.format(config.opsdir, org_id)).read())
    accounts = json.load(open(ACCOUNTS_FILE.format(config.opsdir, org_id)))
    # Add information about the accounts
    org['account_descriptions'] = {a['Code']: a['Description'] for a in accounts}
    generate_pdfs(org, users, transactions)


if __name__ == '__main__':
    root = os.path.abspath(os.path.dirname(__file__) + '/../..')
    os.chdir(root)
    set_context(root, 'giftenoverzicht')

    from giften import generate_pdfs
    import model
    from admingen import config

    print(config.opsdir)
    #sys.exit(0)
    model.openDb('sqlite://%s/overzichtgen.db' % config.opsdir)

    org = getDefaultOrg()
    if org:
        run(org)

