#!/usr/bin/env python3

import json
from decimal import Decimal

from admingen import config

from .giften import generate_overviews
from . import model


USERS_FILE = '{}/{}.users.json'
TRANSACTIONS_FILE = '{}/{}.transactions.json'
ACCOUNTS_FILE = '{}/{}.accounts.json'


def getDefaultOrg():
    with model.sessionScope():
        organisations = [o for o in model.Organisation.select()]
    if len(organisations) == 1:
        return organisations[0]

def generate_pdfs(org):
    org_id = org.id
    transactions = json.loads(open(TRANSACTIONS_FILE.format(config.opsdir, org_id)).read(), parse_float=Decimal)
    users = json.loads(open(USERS_FILE.format(config.opsdir, org_id)).read())
    accounts = json.load(open(ACCOUNTS_FILE.format(config.opsdir, org_id)))
    org_dict = org.to_dict(with_lazy=True)
    # Add information about the accounts
    org_dict['account_descriptions'] = {a['Code']: a['Description'] for a in accounts}
    generate_pdfs(org_dict, users, transactions)

org = getDefaultOrg()
if org:
    generate_pdfs(org)
