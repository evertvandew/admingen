"""

Documentation PayPal API:
https://developer.paypal.com/docs/classic/api/apiCredentials/#credential-types
PayPal SDK (nieuw) : https://github.com/paypal/PayPal-Python-SDK

"""
import time
import asyncio
import datetime
from collections import namedtuple
import os
import sys
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP
import traceback
from enum import IntEnum
from typing import List, Tuple, Dict, Any
import re
import threading

from admingen.servers import mkUnixServer, Message, expose, serialize, deserialize, update
from admingen import config
from admingen.logging import log_exceptions
from admingen.clients.paypal import (downloadTransactions, pp_reader, PPTransactionDetails,
                                     PaypalSecrets, DataRanges, period2dt)
from admingen.clients.exact_xml import uploadTransactions, OAuthDetails, OAuth2, FileTokenStore
from admingen import logging
from admingen.db_api import the_db, sessionScope, DbTable, select, Required, Set, openDb, orm
from admingen.international import SalesType, PP_EU_COUNTRY_CODES
from dataclasses import dataclass, fields, asdict
from admingen.worker import Worker




# TODO: Periodically clean up the cache

class PaypalExactTask:
    """ Produce exact transactions based on the PayPal transactions """
    config: [paypal_export_config]
    optional_config: [zeke.ZekeDetails]
    optional_secrets: [zeke.ZekeSecrets]

    def __init__(self, task_id, config_details, exact_secrets: OAuthDetails, pp_login: PaypalSecrets):
        self.task_id = task_id
        self.exact_secrets = exact_secrets
        self.pp_login = pp_login
        # TODO: Handle the optional secrets
        self.config: paypal_export_config = config_details if isinstance(config_details, paypal_export_config) \
            else config_details[0]

        self.classifier = None
        if isinstance(config_details, list) and len(config_details) > 1:
            for option in config_details[1:]:
                if isinstance(option, zeke.ZekeDetails):
                    self.classifier = zeke.classifySale

        # TODO: Handle the optional configuration

        self.pp_username = self.pp_login.username

        # Ensure the download directory exists
        if not os.path.exists(config.downloaddir):
            os.mkdir(config.downloaddir)

    @log_exceptions
    def run(self, period: DataRanges=DataRanges.YESTERDAY, fname=None, start_balance:Decimal=None,
            test=False):
        """ The actual worker. Loads the transactions for yesterday and processes them """
        print ('RUNNING')

        # Load the transaction from PayPal
        #fname = '/home/ehwaal/admingen/downloads/Download (1).CSV'
        if not fname:
            fname = downloadTransactions(self.pp_login, period)
        #fname = downloadTransactions(self.pp_login, period)
        logging.info('Processing transactions from %s'%os.path.abspath(fname))
        #zeke_details = zeke.loadTransactions()
        with sessionScope():
            period_start, period_end = period2dt(period)
            batch = PaypalExchangeBatch(task_id=self.task_id,
                                        timestamp=datetime.datetime.now(),
                                        period_start=period_start,
                                        period_end = period_end)

            transactions, xml = self.convertTransactions(self.detailsGenerator(fname, batch))

            # If there are no transactions, quit
            if len(transactions) == 0:
                return

            # Check the transactions...
            if start_balance is None:
                sum_first = sum(l.Amount for l in transactions[0].lines
                                if l.GLAccount==self.config.pp_account)
                start_balance = transactions[0].closingbalance - sum_first
            balance = start_balance
            for t in transactions:
                s = sum(l.Amount for l in t.lines
                                if l.GLAccount==self.config.pp_account)
                balance += s
                assert balance == t.closingbalance, 'No connection for transaction %s'%t
            # Start_balance now contains the closing balance...

            # Generate the accompanying XML
            batch.closing_balance = balance
            batch.starting_balance = start_balance
            fname = 'exact_transactions.xml'
            with open(fname, 'w') as of:
                of.write(xml)
            total = sum(sum(l.Amount for l in t.lines if l.GLAccount==self.config.pp_account)
                        for t in transactions)
            logging.info('Written exact transactions to %s: %s\t%s'%(os.path.abspath(fname), len(transactions), total))

            # Upload the XML to Exact
            if test:
                batch.success, batch.warnings, batch.errors, batch.fatals = [1, 2, 3, 4]
                return
            else:
                store = FileTokenStore('exacttoken_%s.json'%self.config.customerid)
                oa = OAuth2(store, self.exact_secrets)
                counts = uploadTransactions(oa, self.config.administration_hid, fname)
                logging.info('Uploaded transactions to exact division %s: %s'%(self.config.administration_hid, counts))
                batch.success, batch.warnings, batch.errors, batch.fatals = counts


if __name__ == '__main__':
    config.load_context()
    worker = Worker(PaypalExactTask)
    print('Worker starting')
    worker.run()
