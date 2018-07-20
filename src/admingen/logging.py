""" Some utilities for logging.
    The actual log handlers etc. are set in admingen.config.
"""

import sys
import logging, logging.handlers
import traceback



info = logging.info
debug = logging.debug
warning = logging.warning
error = logging.error
exception = logging.exception


# By default, log to both stdout and to syslog
log = logging.getLogger()
log.setLevel(logging.DEBUG)

handler1 = logging.handlers.SysLogHandler('/dev/log')
fmt = logging.Formatter(sys.argv[0]+' - %(module)s.%(funcName)s (%(levelname)s): %(message)s')
handler1.setFormatter(fmt)
log.addHandler(handler1)



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