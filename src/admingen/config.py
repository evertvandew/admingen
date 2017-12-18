

import os
import os.path
import sys
import argparse
import re
from configobj import ConfigObj
import json
from io import StringIO
from string import Template


theconfig = {}
configdir = '.'


def confparser(s):
    """ CONF files all consist of lines with <key> <value> pairs.
        Unix conventions on quoting and comments are followed.
    """
    comments_re = r'(^[^#]*)'
    def reader():
        while True:
            k = next(tokens)
            v = next(tokens)
            yield k, v
    return {k:v for k, v in reader()}




config_parsers = {'.ini': lambda s: ConfigObj(StringIO(s)), '.json': json.loads,
                  '.conf': confparser}

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
    """ We are still developing... """
    return True


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
    """
    # The path is derived from the class name, but in lowercase
    # and with all occurences of 'config' removed.
    path = cls.__name__.lower().replace('config', '')
    # There may already be values in the config: use them!
    init = theconfig.get(path, {})
    config = cls(**init)
    # Overwrite any existing config, so it gets the correct type.
    theconfig[path] = config

    def update(kwargs):
        new_config = cls(**kwargs)
        config.__dict__.update(new_config.__dict__)
    config.update = update
    def factory():
        return config
    return factory



def test():
    s = '''# Automatically created by the clamav-freshclam postinst
# Comments will get lost when you reconfigure the clamav-freshclam package

DatabaseOwner clamav
UpdateLogFile /var/log/clamav/freshclam.log
LogVerbose false
LogSyslog false
LogFacility LOG_LOCAL6
LogFileMaxSize 0
LogRotate true
LogTime true
Foreground false
Debug false
MaxAttempts 5
DatabaseDirectory /var/lib/clamav
DNSDatabaseInfo current.cvd.clamav.net
AllowSupplementaryGroups false
ConnectTimeout 30
ReceiveTimeout 30
TestDatabases yes
ScriptedUpdates yes
CompressLocalDatabase no
SafeBrowsing false
Bytecode true
NotifyClamd /etc/clamav/clamd.conf
# Check for new database 24 times a day
Checks 24
DatabaseMirror db.local.clamav.net
DatabaseMirror database.clamav.net
'''
    d = confparser(s)
    print (d)


if __name__ == '__main__':
    test()