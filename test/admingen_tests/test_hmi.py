
from unittest import TestCase

from tatsu.ast import AST

from admingen.hmi import createServices
from pony.orm import db_session, select, commit


class HMITest(TestCase):
    @classmethod
    def setUpClass(cls):
        """ Create a parser and parse the test case """
        with open('uren_crm.txt') as f:
            cls.ast = model.parse(f.read(), start='projects', whitespace=r'[ \t\r]')

    def testHMI(self):
        """ Instantiate the HMI and walk through it """
        hmi = createServices(self.ast)