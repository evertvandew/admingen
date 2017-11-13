
import time
import threading
import datetime
from collections import namedtuple
import paypalrestsdk
from paypalrestsdk.payments import Payment
from admingen.servers import runUnixServer, unixproxy
from admingen.keyring import KeyRing


class paypallogin:
    client_id : str
    client_password : str
    client_cert : bytes

class exactlogin:


class taskdetails:
    paypallogin: paypallogin
    exactlogin: exactlogin
    administration: int
    paypalbook: int



class Worker:
    keyring = None
    tasks = {}
    def unlock(self, password):
        self.keyring = KeyRing('test.enc', password)
    def status(self):
        return dict(keyring='unlocked' if self.keyring else 'locked',
                    tasks=[t.name for t in self.tasks])
    def newtask(self, **details):
        details = taskdetails(**details)
        self.tasks[details.name] = details
        self.keyring[details.name] = details


def run():
    runUnixServer(Worker(), 'blablabla')



def isostr(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

def readNewApi():
    api = paypalrestsdk.api.Api(mode='live', **login._asdict())


    start = datetime.datetime.utcnow() - datetime.timedelta(2)

    payments = Payment.all({'count': 10,
                            'start_time': isostr(start),
                            'end_time': isostr(datetime.datetime.utcnow()),
                            'start_index': 0,}, api)
    print (payments)

