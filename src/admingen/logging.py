""" Some utilities for logging.
    The actual log handlers etc. are set in admingen.config.
"""

import logging
import traceback


def log_limited(func):
    """ Log the message for any exception that occurs """
    def doIt(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.error(str(e))
    return doIt


def log_exceptions(func):
    """ Log the full details for any exception """
    def doIt(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            logging.exception('')
            traceback.print_exc()
    return doIt