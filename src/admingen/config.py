

import os
import sys
import argparse
from configobj import ConfigObj


def testmode():
    """ We are still developing... """
    return True


def getConfig(path, default):
    """ Get a specific configuration item """
    return default

def fname():
    p = argparse.ArgumentParser()
    p.add_argument('-c', '--config',
                   default=os.environ.get('CONFIG_FILE', 'config.ini'))
    n = p.parse_args()
    return n.config



