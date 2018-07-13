
import datetime
import requests
import xml.etree.ElementTree as ET
from decimal import Decimal

from admingen.logging import log_limited, logging
from admingen.keyring import KeyRing
from admingen.clients.rest import OAuth2, OAuthDetails, FileTokenStore
from admingen.dataclasses import dataclass


TOPICS = ["Accounts",
        "ActivitySectors",
        "Administrations",
        "Agencies",
        "AllocationRules",
        "APs",
        "ARs",
        "AssetGroups",
        "Assets",
        "Balances",
        "BankLinks",
        "Budgets",
        "BudgetScenarios",
        "BusinessTypes",
        "CompanySizes",
        "Costcenters",
        "Costunits",
        "DDMandates",
        "Departments",
        "DepreciationMethods",
        "Documents",
        "Employees",
        "Employments",
        "EntryTemplates",
        "EntryTemplateTransactions",
        "ExchangeRates",
        "FinYears",
        "GLAccountCategories",
        "GLAccountClassifications",
        "GLAccounts",
        "GLTransactions",
        "HRMSubscriptions",
        "Indicators",
        "Invoices",
        "Items",
        "JobGroups",
        "JobTitles",
        "Journals",
        "Layouts",
        "LeadPurposes",
        "LeadRatings",
        "Leads",
        "LeadSources",
        "LeadStages",
        "ManufacturedBillofMaterials",
        "MatchSets",
        "Opportunities",
        "OpportunityStages",
        "PaymentConditions",
        "PayrollComponentGroups",
        "PayrollComponents",
        "PayrollEntries",
        "PayrollGLLinks",
        "PayrollYears",
        "PeriodProcessReports",
        "Quotations",
        "ReasonCodes",
        "SalesTypes",
        "Settings",
        "ShippingMethods",
        "Templates",
        "Titles",
        "UserAdministrations",
        "Users",
        "VATs"]


@dataclass
class TransactionLine:
    """ Details of specific transactions """
    AccountCode: str
    AccountName: str
    Date: datetime.datetime
    Amount: Decimal
    Currency: str
    ForeignAmount: Decimal
    ForeignCurrency: str
    GLAccountCode: str
    Description: str
    CostUnit: str
    CostCenter: str
    AssetCode: str
    FinPeriod: int
    FinYear: int
    InvoiceNumber: int
    JournalCode: str
    ProjectCode: str
    VATCode: str
    YourRef: str
    Description: str


@dataclass
class Transaction:
    TransactionType: int
    Journal: int
    Lines: TransactionLine


@dataclass
class Division:
    """ Different administrations grouped under one user account """
    Code: int
    HID: int
    Description: str

@dataclass
class Accounts:
    """ CRM accounts, i.e. the customers / debtors """


@dataclass
class Message:
    """ Response message for a post to Exact """
    type: str
    topic: str
    key: str
    reason: str


class XMLapi:
    base_url = 'https://start.exactonline.nl/docs/'
    download_url = base_url + 'XMLDownload.aspx'
    upload_url = base_url + 'XMLUpload.aspx'
    divisions_url = base_url + 'XMLDivisions.aspx'
    topics = ['GLTransactions', 'Administrations']
    '?Mode=1&Params%24YearRange%24To=2017&Topic=GLTransactions&Params%24EntryDate%24From=++-++-++++&BeginModalCallStack=1&Backwards=0&_Division_=15972&Params%24Status=20%2c50&Params%24YearRange%24From=2017&PagedFromUI=1&IsModal=1&Params%24Period%24From=1&Params%24EntryDate%24To=++-++-++++&Params%24Period%24To=12&PageNumber=4&TSPaging=0x000000019E3E63EF'

    '''https://start.exactonline.nl/docs/XMLDownload.aspx?BeginModalCallStack=1&Params%24StartDate%24From=++-++-++++&_Division_=15972&PagedFromUI=1&Backwards=0&IsModal=1&Params%24StartDate%24To=++-++-++++&Mode=1&Topic=Administrations&PageNumber=1&TSPaging='''

    def __init__(self, oauth : OAuth2):
        self.oauth_headers = oauth

    def get(self, topic, division, **kwargs):
        if topic not in TOPICS:
            return None

        headers = self.oauth_headers()

        params = kwargs.copy()
        params['PageNumber'] = 1
        params['Topic'] = topic
        params['_Division_'] = division
        r = requests.get(self.download_url, params=params, headers=headers)
        if r.status_code != 200:
            return None
        root = ET.fromstring(r.content.decode('utf-8'))
        return root

    def post(self, topic, division, data, **kwargs):
        if topic not in TOPICS:
            return None

        headers = self.oauth_headers()

        params = kwargs.copy()
        params['PageNumber'] = 1
        params['Topic'] = topic
        params['_Division_'] = division
        r = requests.post(self.download_url, data, params=params, headers=headers)
        if r.status_code != 200:
            return None
        root = ET.fromstring(r.content.decode('utf-8'))
        msgs = [Message(m.attrib['type'], m[0].attrib['code'], m[0][0].attrib['key'], m[2].text)
                for m in root[0]]
        return msgs

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

    def getTransactions(self, division, **kwargs):
        def args(node):
            pass
        root = self.get('GLTransactions', division, **kwargs)
        trans = [TransactionLine(**args(t)) for t in root[0]]
        return trans

    def uploadTransactions(self, division, data):
        msgs = self.post('GLTransactions', division, data)
        errors = [m for m in msgs if m.type == '0']
        warnings = [m for m in msgs if m.type == '1']
        successes = [m for m in msgs if m.type == '2']
        fatals = [m for m in msgs if m.type == '3']

        for e in errors + fatals:
            logging.error('Error when uploading transaction: %s'%e)
        for w in warnings:
            logging.warning('Error when uploading transaction: %s'%e)

        return len(successes), len(warnings), len(errors), len(fatals)



@log_limited
def uploadTransactions(oauth_details: OAuth2, hid, fname):
    # Open the API
    api = XMLapi(oauth_details)

    # First translate the HID to the actual administration code
    divs = api.getDivisions()
    d = [d for d in divs if d.HID == hid]
    if len(d) != 1:
        raise RuntimeError('Could not find administration %s!'%hid)
    administration = d[0].Code

    # Now upload the transactions
    with open(fname, 'r') as f:
        data = f.read()
    if api.uploadTransactions(administration, data) / 100 != 2:
        msg = 'An error occurred when uploading %s to %s'%(fname, hid)
        raise RuntimeError(msg)


if __name__ == '__main__':
    pw = input('Please give password for oauth keyring')
    ring = KeyRing('oauthring.enc', pw)
    details = ring['oauthdetails']
    details = OAuthDetails(**details)
    oa = OAuth2(FileTokenStore('temptoken.json'), details, ring.__getitem__)

    xml = XMLapi(oa)
    print (xml.getTransactions(15972))

