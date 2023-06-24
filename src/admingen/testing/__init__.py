"""
This library has two tools for testing. The first is a small improvement to the standard unittest framework.
The second is a new, lightweight test framework that uses decorators to define tests.
"""
from typing import Any
from dataclasses import dataclass
import traceback as tb
from contextlib import contextmanager

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



###############################################################################
## Modern, lightweight test framework inspired by Rust.

@dataclass
class TestResult:
    name: str
    ok: bool
    exception: Any
    msg: str


testcases = []

def testcase(*before, after=None):
    """ Decorator for running test cases """
    def decorator(f):
        def doIt():
            nonlocal before, after
            m1 = 'Before function threw exception'
            m2 = 'Test case failed'
            m3 = 'After function threw exception'
            m4 = 'Test successful'
            print("Starting", f.__name__)
            after = after or []
            for b in before:
                if callable(b):
                    try:
                        b()
                    except:
                        print(m1)
                        return TestResult(f.__name__, False, tb.format_exc(), m1)
            try:
                f()
            except:
                print(m2)
                return TestResult(f.__name__, False, tb.format_exc(), m2)
            if callable(after):
                after = [after]
            for a in after:
                if callable(a):
                    try:
                        a()
                    except:
                        print(m3)
                        return TestResult(f.__name__, False, tb.format_exc(), m3)
            print(m4)
            return TestResult(f.__name__, True, None, m4)

        # Add this function to the list of possible cases
        testcases.append(doIt)
        return doIt
    return decorator

def runall():
    results = [t() for t in testcases]
    failures = [r for r in results if not r.ok]
    successes = [r for r in results if r.ok]

    print(f'\n\nTest summary: {len(results)} cases, {len(failures)} failures, {len(successes)} passed.')

    for r in failures:
        print(f'\n\n\nEXCEPTION FOR {r.name}\n\n{r.msg}\n{r.exception}')

@contextmanager
def expect_exception(e: Exception):
    try:
        yield
    except e:
        return

    assert False, "Action did not throw the expected exception"

running_tests = False

def running_unittests():
    return running_tests
def set_running_unittests(value):
    global running_tests
    running_tests = value