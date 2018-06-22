
import datetime
import requests
import xml.etree.ElementTree as ET

from admingen.keyring import KeyRing
from admingen.clients.rest import OAuth2, OAuthDetails, FileTokenStore
from admingen.dataclasses import dataclass


TOPICS = ['GLTransactions', 'GLAccounts', ]


@dataclass
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

@dataclass
class Division:
    """ Different administrations grouped under one user account """
    Code: int
    HID: int
    Description: str

@dataclass
class Accounts:
    """ CRM accounts, i.e. the customers / debtors """



class XML:
    base_url = 'https://start.exactonline.nl/docs/'
    download_url = base_url + 'XMLDownload.aspx'
    divisions_url = base_url + 'XMLDivisions.aspx'
    topics = ['GLTransactions', 'Administrations']
    '?Mode=1&Params%24YearRange%24To=2017&Topic=GLTransactions&Params%24EntryDate%24From=++-++-++++&BeginModalCallStack=1&Backwards=0&_Division_=15972&Params%24Status=20%2c50&Params%24YearRange%24From=2017&PagedFromUI=1&IsModal=1&Params%24Period%24From=1&Params%24EntryDate%24To=++-++-++++&Params%24Period%24To=12&PageNumber=4&TSPaging=0x000000019E3E63EF'

    '''https://start.exactonline.nl/docs/XMLDownload.aspx?BeginModalCallStack=1&Params%24StartDate%24From=++-++-++++&_Division_=15972&PagedFromUI=1&Backwards=0&IsModal=1&Params%24StartDate%24To=++-++-++++&Mode=1&Topic=Administrations&PageNumber=1&TSPaging='''

    def __init__(self, oauth : OAuth2):
        self.oauth_headers = oauth

    def get(self, topic, **kwargs):
        headers = self.oauth_headers()

        params = kwargs.copy()
        params['PageNumber'] = 1
        r = requests.get(self.download_url, params=params, headers=headers)

    def getDivisions(self):
        headers = self.oauth_headers()
        r = requests.get(self.divisions_url, headers=headers)
        if r.status_code != 200:
            return None
        root = ET.fromstring(r.content.decode('utf-8'))
        divs = [Division(Code=int(div.attrib['Code']),
                                 HID=int(div.attrib['HID']),
                                 Description=div[0].text)
                for div in root]
        return divs


def uploadTransactions(token, administration, fname):
    raise NotImplementedError()


if __name__ == '__main__':
    pw = input('Please give password for oauth keyring')
    ring = KeyRing('oauthring.enc', pw)
    details = ring['oauthdetails']
    details = OAuthDetails(**details)
    oa = OAuth2(FileTokenStore('temptoken.json'), details, ring.__getitem__)

    xml = XML(oa)
    print (xml.getDivisions())
