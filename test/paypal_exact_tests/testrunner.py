
from unittest import TestCase
import selenium
from experiments.paypal_exact import run, worker


class RunnerTests(TestCase):
    def testClient(self):
