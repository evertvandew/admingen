
import os, os.path
from datetime import datetime

from admingen.appengine import readconfig
from admingen import servers
from admingen.db_api import the_db, orm, sessionScope


import unittest

database = 'test.db'

class UrenregTest(unittest.TestCase):
    def setUp(self):
        if os.path.exists(database):
            os.remove(database)
    def test1(self):
        # Read the DSL description of the application
        with open('uren_crm.txt') as f:
            model = readconfig(f)
        # Create some test data
        # We need a real database, in-memory databases don't work with cherrypy's
        the_db.bind(provider='sqlite', filename=database, create_db=True)
        the_db.generate_mapping(create_tables=True)
        orm.sql_debug(True)

        with sessionScope():
            o = the_db.Opdracht(naam='test', start=datetime.now(), state=model.fsmmodel.initial['Opdracht'])
        # Instantiate it
        servers.run_model(model)
