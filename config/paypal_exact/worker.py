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

import paypalrestsdk
from paypalrestsdk.payments import Payment
from admingen.servers import mkUnixServer, Message, expose
from admingen.keyring import KeyRing
from admingen.email import sendmail
from admingen import config
from admingen.clients.rest import OAuth2
from admingen import logging


@Message
class paypallogin:
    administration : int
    paypal_client_id : str
    client_password : str
    client_cert : bytes

@Message
class exactlogin:
    administration : int
    client_id : str
    client_secret : str
    client_token : str


@Message
class taskdetails:
    administration: int
    paypalbook: int


mailconfig = dict(adminmail='evert.vandewaal@xs4all.nl',
              selfmail='paypalchecker@ehud',
              appname='Paypal Exporter',
              keyring='appkeyring.enc')

bootmail = '''I have restarted, and need my keyring unlocked!

Your faithful servant, %s'''

if False:
    # First let the maintainer know we are WAITING!
    sendmail(config['adminmail'], config['selfmail'],
             'Waiting for action',
             bootmail % config['appname'])


class Worker:
    keyring = None
    tasks = {}
    exact_token = None
    oauth = None
    sockname = '/home/ehwaal/tmp/paypalreader.sock' if config.testmode() else \
        '/run/paypalreader/readersock'
    keyringname = '/home/ehwaal/tmp/paypalreader.encr'

    @expose
    def unlock(self, password):
        self.keyring = KeyRing(self.keyringname, password)

        # Now we can access the client secret for OAuth login
        client_id = '49b30776-9a29-4a53-b69d-a578712e997a'
        client_secret = self.keyring[client_id]
        if client_secret:
            self.oauth = OAuth2('https://start.exactonline.nl/api/oauth2/token',
                                client_id,
                                client_secret,
                                'http://paypal_reader.overzichten.nl:13959/oauth_code')
        else:
            logging.error('The client secret has not been set!')

    @expose
    def status(self):
        return dict(keyring='unlocked' if self.keyring else 'locked',
                    tasks=[t.name for t in self.tasks],
                    exact_online='authenticated' if self.exact_token else 'locked')

    @expose
    def addtask(self, details: taskdetails):
        details = taskdetails(**details)
        self.tasks[details.name] = details
        self.keyring[details.name] = details

    @expose
    def setauthorizationcode(self, code):
        """ The authorization is used to get the access token """
        if self.exact_token:
            raise RuntimeError('The system is already authorized')
        token = self.oauth.getAccessToken(code)
        self.exact_token = token

        # Set a timer to refresh the token
        loop = asyncio.get_event_loop()
        loop.call_later(int(token['expires_in']) - 550, self.refreshtoken)

    def refreshtoken(self):
        """ Refresh the current access token """
        token = self.oauth.getAccessToken()
        self.exact_token = token

        # Set a timer to refresh the token again
        loop = asyncio.get_event_loop()
        loop.call_later(int(token['expires_in']) - 550, self.refreshtoken)


    @staticmethod
    @logging.log_exceptions
    def run():
        # In test mode, we need to create our own event loop
        print ('Starting worker')
        if config.testmode():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        server = mkUnixServer(Worker(), Worker.sockname)
        loop = asyncio.get_event_loop()
        loop.create_task(server)
        loop.run_forever()


if __name__ == '__main__':
    print ('Worker starting')
    Worker.run()
