""" Some utilities for logging.
    The actual log handlers etc. are set in admingen.config.
"""

from logging import *
import traceback



def log_exceptions(func):
    def doIt(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            exception('')
            traceback.print_exc()
    return doIt