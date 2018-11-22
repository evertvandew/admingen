
from decimal import Decimal
import datetime
import os.path
import glob

from admingen import db_api
from admingen.clients.exact_xml import processAccounts
from paypal_converter import (PaypalExactConverter, paypal_export_config, classifiers)



class TransactionPersister:
    def __init__(self, dirname):
        # We need a new database
        self.db = db_api.the_db = db_api.orm.Database()
        # Create a cache for storing the details of earlier transactions
        @db_api.DbTable
        class PaypalTransactionLog:
            ref: db_api.Required(str, index=True)
            xref: str
            timestamp: datetime.datetime
            exact_transaction: db_api.Required('ExchangeTransactionLog')

        @db_api.DbTable
        class ExchangeTransactionLog:
            pp_transactions: db_api.Set(PaypalTransactionLog)
            amount: Decimal
            vat_percent: Decimal
            account: int
            batch: db_api.Required('PaypalExchangeBatch')

        # Keep track of when transactions were last retrieved from PayPal
        @db_api.DbTable
        class PaypalExchangeBatch:
            task_id: int
            timestamp: datetime.datetime
            period_start: datetime.date
            period_end: datetime.date
            starting_balance: Decimal
            closing_balance: Decimal
            fatals: int
            errors: int
            warnings: int
            success: int
            transactions: db_api.Set(ExchangeTransactionLog)

        self.PaypalTransactionLog = PaypalTransactionLog
        self.ExchangeTransactionLog = ExchangeTransactionLog
        self.PaypalExchangeBatch = PaypalExchangeBatch

        self.batch: PaypalExchangeBatch = None
        db_api.openDb('sqlite://%s/transactionlog.db'%dirname)

    def startBatch(self, **kwargs):
        if 'timestamp' not in kwargs:
            kwargs['timestamp'] = datetime.datetime.now()
        for k in ['errors', 'fatals', 'warnings', 'success']:
            kwargs[k] = 0
        db_api.sessionScope.__enter__()
        self.batch = self.PaypalExchangeBatch(**kwargs)

    def endBatch(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self.batch, k, v)
        db_api.sessionScope.__exit__()

    def exchangeTransactionLog(self, **kwargs):
        transaction = self.ExchangeTransactionLog(batch=self.batch, **kwargs)
        return transaction
    def paypalTransactionLog(self, exch_transaction, **kwargs):
        pp_transaction = self.PaypalTransactionLog(exact_transaction=exch_transaction,
                                                   **kwargs)
        return pp_transaction


def handleDir(path, task_index):
    import glob
    from admingen.data import DataReader
    home = path+'/task_%i'%task_index

    paypals = glob.glob(home+'/Download*.CSV')
    with open(home+'/Accounts_1.xml') as f:
        accounts = processAccounts(f)
    data = DataReader('/home/ehwaal/admingen/projects/paypal_exact/taskconfig.csv')
    config = data['TaskConfig'][task_index]
    config = paypal_export_config(**config.__dict__)
    config.persist = TransactionPersister(home)

    email_2_accounts = {email: account for account in accounts for email in account.email}

    classifier_config = data['Classifier'].get(task_index, None)
    if classifier_config:
        name = classifier_config.classifier_name
        config.classifier = classifiers[name](home, classifier_config.details)

    for i, fname in enumerate(paypals):
        config.persist.startBatch(task_id=task_index,
                                  period_start=None,
                                  period_end=None,
                                  starting_balance=Decimal(0),
                                  closing_balance=Decimal(0))
        converter = PaypalExactConverter(config)
        transactions = converter.groupedDetailsGenerator(fname, email_2_accounts)
        ofname = os.path.dirname(fname) + '/upload_%s.xml'%(i+1)
        with open(ofname, 'w') as of:
            converter.generateExactTransactionsFile(transactions, of)

        config.persist.endBatch(fatals=0, errors=0, warnings=0, success=0)


if __name__ == '__main__':
    handleDir('/home/ehwaal/tmp/pp_export/test-data', 3)
