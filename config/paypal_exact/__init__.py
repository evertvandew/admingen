""" Run a server that writes paypal transactions to exact """

import secrets
from collections import namedtuple
import requests
import cherrypy
import time
import threading

from admingen.servers import OAuthChecker
from admingen.config import loadconfig, config
from admingen import keyring
from admingen.logging import log_exceptions
from admingen.servers import unixproxy

from .worker import Worker


config = dict(adminmail='evert.vandewaal@xs4all.nl',
              selfmail='paypalchecker@ehud',
              appname='Paypal Exporter',
              keyring='appkeyring.enc')


bootmail = '''I have restarted, and need my keyring unlocked!
             
Your faithful servant, %s'''





def run():
    loadconfig()

    # First let the maintainer know we are WAITING!
    sendmail(config['adminmail'], config['selfmail'],
             'Waiting for action',
             bootmail%config['appname'])

    worker = unixproxy(Worker)

    class TaskHandler:
        tasks_details = {}
        task_threads = {}

        @cherrypy.expose
        def index(self):
            return 'Hello, world!'

        def startTask(self, user_id):

