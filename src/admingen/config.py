

import os
import os.path
import sys
import argparse
import re
from configobj import ConfigObj
import json
from io import StringIO
from string import Template
from inspect import signature
import logging
import logging.handlers

theconfig = {}
configdir = '.'


config_parsers = {'.ini': lambda s: ConfigObj(StringIO(s)), '.json': json.loads,
                  '.conf': None}

def configfiles():
    """ Generator that returns the full paths to configuration files """
    for dirpath, dirnames, fnames in os.walk(configdir):
        for fname in fnames:
            if os.path.splitext(fname)[1] in config_parsers:
                yield os.path.join(dirpath, fname)



def set_configdir(p):
    global configdir
    configdir = os.path.abspath(p)
    load()


def parse(fname):
    parser = config_parsers[os.path.splitext(fname)[1]]
    with open(fname) as f:
        # Substitute global variables
        txt = f.read()
        t = Template(txt)
        d = os.environ.copy()
        d['CONFDIR'] = configdir
        s = t.safe_substitute(d)
        return parser(s)


def load():
    global theconfig
    for fname in configfiles():
        logging.info('Loading config file %s'%fname)
        path = os.path.splitext(fname)[0]
        path = os.path.relpath(path, configdir)
        parts = path.split(os.pathsep)
        conf = theconfig
        newconf = parse(fname)
        for part in parts[:-1]:
            conf = conf.setdefault(part, {})
        if parts[-1] in conf:
            conf[parts[-1]].update(newconf)
        else:
            conf[parts[-1]] = newconf


def testmode():
    """ Test whether we are running deployed or not.
        When deployed, several environment variables will be set.
    """
    return 'PROJECTNAME' not in os.environ


def getConfig(path, default=None):
    """ Get a specific configuration item """
    parts = path.split('.')
    conf = theconfig
    for part in parts[:-1]:
        conf = conf.setdefault(part, {})
    return conf.get(parts[-1], default)

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
        The configuration is a singleton. Instantiating it returns the
        one and only configuration object.
    """
    def default_constructor(self, **kwargs):
        self.__dict__.update(kwargs)
    def convert_types(d):
        """ Ensure the provided configuration set is of the right type """
        result = {}
        for k, v in d.items():
            original = getattr(cls, k)
            if type(original) == bool and type(v) == str:
                # Decide that value based on the first character: Yes or True.
                result[k] = v[0].lower() in ['y', 't']
            else:
                result[k] = type(original)(v)
        return result

    def update(kwargs):
        """ Update the value of the configuration. """
        new_config = cls(**convert_types(kwargs))
        config.__dict__.update(new_config.__dict__)

    def factory():
        """ The function called when a user tries to instantiate the config
            class. It returns the configuration singleton.
        """
        return config

    # Ensure the class has a constructor that accepts parameters.
    sig = signature(cls)
    if not sig.parameters:
        cls.__init__ = default_constructor

    # The path is derived from the class name, but in lowercase
    # and with all occurences of 'config' removed.
    path = cls.__name__.lower().replace('config', '')
    # There may already be values in the config: use them!
    init = theconfig.get(path, {})
    config = cls(**convert_types(init))
    # Overwrite any existing config, so it gets the correct type.
    theconfig[path] = config

    config.update = update
    return factory


projectname = os.environ.get('PROJECTNAME', os.path.basename(sys.argv[0]))
logdir = os.environ.get('LOGDIR', '') or os.getcwd()
opsdir = os.environ.get('OPSDIR', '') or os.getcwd()
rundir = os.environ.get('RUNDIR', '') or os.getcwd()

downloaddir = os.path.join(rundir, 'downloads')


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# add ch to logger
logger.addHandler(ch)

if not testmode():
    # create file handler and set level to warning
    logfile = os.path.join(logdir, projectname+'.log')
    ch = logging.handlers.RotatingFileHandler(logfile, maxBytes=10e6, backupCount=5)
    ch.setLevel(logging.WARNING)
    formatter = logging.Formatter('%(asctime)s - %(filename)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(ch)
