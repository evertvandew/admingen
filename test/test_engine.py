
from io import StringIO
from datetime import datetime, date, time, timedelta
from unittest import TestCase

import tatsu

from admingen.dbengine import readconfig, engine, Message, model
from pony.orm import db_session, select


class EngineTests(TestCase):
    @classmethod
    def setUpClass(cls):
        """ Create a parser and parse the test case """
        with open('uren_crm.txt') as f:
            cls.ast = model.parse(f.read(), start='config', whitespace=r'[ \t\r]')
    def testSyntax(self):
        """ Test whether the parser can handle the test examples """
        ast = self.ast
        self.assertEqual(len(ast['modules']), 1)
        self.assertEqual(len(ast['fsms']), 3)
        self.assertEqual(len(ast['actions']), 1)
        self.assertEqual(len(ast['tables']), 8)
        self.assertEqual(len(ast['rules']), 3)
        print(ast)

    def testMessaging(self):
        """ Test message handling """
        with open('uren_crm.txt') as f:
            transitions, db, model = readconfig(f)
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