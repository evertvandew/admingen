
from unittest import TestCase
import selenium
from projects.paypal_exact import run, worker


class RunnerTests(TestCase):
    def testClient(self):
