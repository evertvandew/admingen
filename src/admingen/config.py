

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
configdir = os.environ.get('CONFDIR', '.')


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


def substituteContext(txt):
    """ Substitute strings in the form $ENVVAR with the contents of this variable in the config """
    d = os.environ.copy()
    d.update({'CONFDIR': configdir,
              'RUNDIR': rundir,
              'OPSDIR': opsdir,
              'LOGDIR': logdir})

    j = Template(txt)
    s = j.safe_substitute(d)
    return s


def parse(fname):
    parser = config_parsers[os.path.splitext(fname)[1]]
    with open(fname) as f:
        # Substitute global variables
        txt = f.read()
        s = substituteContext(txt)
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
    """ Decorator that turns a config specification (dataclass) into a getter for
        accessing the configuration. The configuration is returned as
        an object of type cls.
        The configuration is a singleton. Instantiating it returns the
        one and only configuration object.
        The config specification is a regular object, but also has the dictionary protocol
    """
    def asdict(o):
        if isinstance(o, dict):
            return o
        return o.__dict__
    def default_constructor(self, **kwargs):
        # Include the default values and current values
        d = cls.__dict__.copy()
        # Delete any variables starting with __
        for k in [k for k in d.keys() if k.startswith('__')]:
            del d[k]
        # Overwrite with the values given by the called
        d.update(kwargs)
        # Substitute values for environment variables
        txt = json.dumps(d)
        txt = substituteContext(txt)
        kwargs = json.loads(txt)
        # Apply the updated values
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

    @staticmethod
    def update(kwargs):
        """ Update the value of the configuration. """
        new_config = cls(**convert_types(kwargs))
        config.__dict__.update(new_config.__dict__)

    def factory():
        """ The function called when a user tries to instantiate the tmp
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
    config = cls(**convert_types(asdict(init)))
    # Overwrite any existing tmp, so it gets the correct type.
    theconfig[path] = config

    cls.update = update
    return factory

projectname = logdir = opsdir = rundir = downloaddir = projdir = rootdir = ''

def load_context():
    global projectname, logdir, opsdir, rundir, downloaddir, projdir, rootdir

    # Define a number of variables for accessing the file system.
    # These directories can be set by environment variables, and default to the cwd.
    # LOGDIR: the directory where log files are to be stored, e.g. /var/log/<project>.
    # OPSDIR: the directory where operational files are to be stored, such as databases and UNIX sockets
    #         e.g. /var/lib/<project>
    # RUNDIR: the context where a program lives, e.g. a HOME directory or /run/<project>.
    # CONFDIR: the directory where config files live, e.g. /etc/project
    projectname = os.environ.get('PROJECTNAME', os.path.basename(sys.argv[0]))
    rootdir = os.environ.get('ROOTDIR') or os.path.abspath(os.path.dirname(__file__)+'/../..')
    logdir = os.environ.get('LOGDIR') or os.getcwd()
    opsdir = os.environ.get('OPSDIR') or os.getcwd()
    rundir = os.environ.get('RUNDIR') or os.getcwd()
    projdir = os.environ.get('PROJDIR') or rootdir + '/projects/' + projectname

    downloaddir = os.path.join(rundir, 'downloads')

    # TODO: Ensure reload of configuration files


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

load_context()