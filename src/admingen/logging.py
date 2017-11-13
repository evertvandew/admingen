

import logging



def log_exceptions(func):
    def doIt(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            logging.exception('')

