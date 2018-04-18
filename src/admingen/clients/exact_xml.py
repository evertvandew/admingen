
import datetime
import requests

from admingen.clients.rest import OAuth2

class TransactionLine:
    """ Details of specific transactions """
    AccountCode: str
    AccountName: str
    Date: datetime.datetime
    AmountDC: float
    EntryNumber: int
    GLAccountCode: str
    Description: str
    CostUnit: str
    CostCenter: str
    AssetCode: str
    FinancialPeriod: int
    FinancialYear: int
    InvoiceNumber: int
    JournalCode: str
    ProjectCode: str
    Type: int
    VATCode: str
    YourRef: str

class Division:
    """ Different administrations grouped under one user account """

class Accounts:
    """ CRM accounts, i.e. the customers / debtors """



class XML:
    download_url = 'https://start.exactonline.nl/docs/XMLDownload.aspx'
    topics = ['GLTransactions', 'Administrations']
    '?Mode=1&Params%24YearRange%24To=2017&Topic=GLTransactions&Params%24EntryDate%24From=++-++-++++&BeginModalCallStack=1&Backwards=0&_Division_=15972&Params%24Status=20%2c50&Params%24YearRange%24From=2017&PagedFromUI=1&IsModal=1&Params%24Period%24From=1&Params%24EntryDate%24To=++-++-++++&Params%24Period%24To=12&PageNumber=4&TSPaging=0x000000019E3E63EF'

    '''https://start.exactonline.nl/docs/XMLDownload.aspx?BeginModalCallStack=1&Params%24StartDate%24From=++-++-++++&_Division_=15972&PagedFromUI=1&Backwards=0&IsModal=1&Params%24StartDate%24To=++-++-++++&Mode=1&Topic=Administrations&PageNumber=1&TSPaging='''

    def __init__(self, oauth : OAuth2):
        self.oauth = oauth

    def get(self, topic, **kwargs):
        headers = self.oauth.headers()

        params = kwargs.copy()
        params['PageNumber'] = 1
        r = requests.get(self.download_url, params=params, headers=headers)


def uploadTransactions(token, administration, fname):
    raise NotImplementedError()