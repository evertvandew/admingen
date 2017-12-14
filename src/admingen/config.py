

import os
import sys
import argparse
from configobj import ConfigObj


theconfig = {}
configdir = '.'


def set_configdir(p):
    global configdir
    configdir = p


def testmode():
    """ We are still developing... """
    return True


def getConfig(path, default):
    """ Get a specific configuration item """
    return default

def fname():
    p = argparse.ArgumentParser()
    p.add_argument('-c', '--projects',
                   default=os.environ.get('CONFIG_FILE', 'projects.ini'))
    n = p.parse_args()
    return n.config

def configtype(cls):
    """ Decorator that turns a projects specification into a getter for
        accessing the configuration. The configuration is returned as
        an object of type cls.
    """
    path = cls.__name__
    config = cls()
    theconfig[path] = config

    def update(kwargs):
        new_config = cls(**kwargs)
        config.__dict__.update(new_config.__dict__)
    config.update = update
    def factory():
        return config
    return factory

