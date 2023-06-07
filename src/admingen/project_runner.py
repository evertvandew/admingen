#!/usr/bin/env python3
""" Run a specific project """

import argparse
import os.path
import os
import sys
import importlib
import logging


dir_locations = ['{home}/var/{dir}',
                 '/var/{dir}/{project}',
                 '{curdir}/{dir}',
                 '{curdir}']


def find_dir(dirname, project=None, curdir=None, home=None, create_dir=False, locations=None):
    """ Find a system directory, or optionally create one.
        Returns the directory found.
    """
    # If necessary, find the default values for the environment
    project = project or os.environ['PROJECTNAME']
    curdir = curdir or os.getcwd()
    home = home or os.environ['HOME']
    locations = locations or dir_locations
    # Now go through the various acceptable locations for system directories
    for d_t in locations:
        d = d_t.format(dir=dirname, curdir=curdir, home=home, project=project)
        if os.path.exists(d):
            return d
        if create_dir:
            # Try to create the required directories
            try:
                # The directories are inaccessible for other users
                os.mkdir(d, mode=0o700)
                return d
            except:
                print('Could not create directory', d)
    raise RuntimeError('Could not find a suitable directory')


def env_setdefault(envname, default, create_dir, locations=None):
    """ Check if an environment variable exists. If not, set it with a system
        directory.
    """
    if not envname in os.environ:
        dirname = find_dir(default, create_dir=create_dir, locations=locations)
        os.environ[envname] = dirname


def set_context(root, project, create_dirs=False, testmode=False):
    root = os.path.abspath(root)
    logging.getLogger().setLevel(logging.DEBUG)
    # Check the project exists
    proj_dir = os.path.join(root, 'projects', project)
    assert os.path.exists(proj_dir), 'Project %s does not exist'%project

    os.environ['ROOTDIR'] = os.path.abspath(root)
    os.environ['PROJDIR'] = os.path.abspath(proj_dir)
    os.environ['SRCDIR'] = os.path.abspath(root + '/src')
    os.environ['PROJECTNAME'] = project

    envdirs = []
    env_setdefault('OPSDIR', 'lib', create_dirs)
    env_setdefault('LOGDIR', 'log', create_dirs)
    env_setdefault('RUNDIR', 'lib', create_dirs)
    config_locations = ['{home}/etc/{project}', '/etc/{project}']
    env_setdefault('CONFDIR', 'etc', create_dirs, locations=config_locations)

    if testmode:
        os.environ['TESTMODE'] = '1'

    # Load the configuration
    from admingen import config
    config.set_configdir(os.environ['CONFDIR'])


def run_project(root, args = sys.argv[1:]):
    root = os.path.abspath(root)
    logging.getLogger().setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('project', help='The project to run')
    parser.add_argument('--create-dirs', action='store_true')
    parser.add_argument('--testmode', '-t', action='store_true')
    #parser.add_argument('--root', help='Root directory for the code', default=root)

    args = parser.parse_args(args)
    print (args)

    set_context(root, args.project, args.create_dirs, args.testmode)

    print('Using ops and log directories', os.environ['OPSDIR'], os.environ['LOGDIR'])
    # Look for the configuration
    confdir = os.environ['CONFDIR']

    # Load the project as a library
    mod = importlib.import_module(args.project)

    # Make the project directory the current directory
    print ('Moving to directory', os.environ['PROJDIR'])
    os.chdir(os.environ['PROJDIR'])

    # Run the project
    print ('Starting project', args.project)
    mod.run()
