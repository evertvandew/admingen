
from io import StringIO
from datetime import datetime, date, time, timedelta
from unittest import TestCase

from admingen.dbengine import readConfig, engine, Message
from pony.orm import db_session, select


class EngineTests(TestCase):
    def testMessaging(self):
        """ Test message handling """
        with open('uren_crm.txt') as f:
            transitions, db, model = readConfig(f)
        # Instantiate the database
        db.bind(provider='sqlite', filename=':memory:')
        db.generate_mapping(create_tables=True)

        # Execute a few test messages
        handle = engine(transitions, model)
        handle(Message(method = 'add',
                       path = 'Opdracht',
                       details = dict(naam='DRIS Neckerspoel',
                            omschrijving='Kleine uitbreidingen voor Dynamisch Busstation Neckerspoel',
                            start=date(2017,10,1),
                            end=date(2018, 1, 1))))

        with db_session:
            self.assertEqual(len(select(o for o in model['Opdracht'])), 1)

    def testDefaults(self):
        """ Test if the default property is properly set in the database """

    def testRules(self):
        """ Test if the rules are properly guarded """