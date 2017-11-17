

import os
import sys
import argparse
from configobj import ConfigObj


def testmode():
    """ We are still developing... """
    return True


def fname():
    p = argparse.ArgumentParser()
    p.add_argument('-c', '--config',
                   default=os.environ.get('CONFIG_FILE', 'config.ini'))
    n = p.parse_args()
    return n.config



