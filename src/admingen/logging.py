

from logging import *



def log_exceptions(func):
    def doIt(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            exception('')
    return doIt