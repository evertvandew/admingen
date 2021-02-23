

import unittest


class AdmingenTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for base in cls.__bases__[1:]:
            if hasattr(base, 'setUpClass'):
                base.setUpClass(cls)

    @classmethod
    def tearDownClass(cls) -> None:
        for base in cls.__bases__[1:]:
            if hasattr(base, 'setUpClass'):
                base.tearDownClass(cls)
