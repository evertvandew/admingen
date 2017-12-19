
from decimal import Decimal
from unittest import TestCase

from admingen import config


class ConfigTests(TestCase):
    def test1(self):
        # Give an initial configuration
        config.theconfig = {
            'a':
                {'i':'5678',
                 's': 'blablabla',
                 'sw': 'yes',
                 'f': '3.141592654',
                 'd': '2.12'
                 }}

        # Define a new configuration class
        @config.configtype
        class AConfig:
            i = 1234
            s = 'Hello, World!'
            sw = True
            f = 1.23456
            d = Decimal('1.23')

        # Read the configuration
        conf = AConfig()

        self.assertEqual(conf.i, 5678)
        self.assertEqual(conf.s, 'blablabla')
        self.assertEqual(conf.sw, True)
        self.assertAlmostEqual(conf.f, 3.141592654)
        self.assertEqual(conf.d, Decimal('2.12'))
        pass
