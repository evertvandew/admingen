#!/usr/bin/env python3.6
""" Run a specific project """

import argparse
import os.path
import os
import sys
import importlib
import logging



def run_project(root, args = sys.argv[1:]):
    root = os.path.abspath(root)
    logging.getLogger().setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('project', help='The project to run')
    parser.add_argument('--create-dirs', action='store_true')
    #parser.add_argument('--root', help='Root directory for the code', default=root)

    args = parser.parse_args(args)
    print (args)

    # Check the project exists
    proj_dir = os.path.join(root, 'projects', args.project)
    assert os.path.exists(proj_dir), 'Project %s does not exist'%args.project

    os.environ['ROOTDIR'] = os.path.abspath(root)
    os.environ['PROJDIR'] = os.path.abspath(proj_dir)
    os.environ['SRCDIR'] = os.path.abspath(root + '/src')
    os.environ['PROJECTNAME'] = args.project



    # Find a working directory for storing logs and operational files
    # Fallback is the cwd
    patterns = [os.environ['HOME']+'/var/{type}',
                '/var/{type}/%s'%args.project,
                os.getcwd()+'/{type}',
                os.getcwd()]


    envdirs = []
    if 'OPSDIR' not in os.environ:
        envdirs.append(('OPSDIR', 'lib'))
    if 'LOGDIR' not in os.environ:
        envdirs.append(('LOGDIR', 'log'))


    for p in patterns:
        success = True
        for e, t in envdirs:
            path = p.format(type=t)

            if not os.path.exists(path):
                if args.create_dirs:
                    # Try to create the required directories
                    try:
                        # The directories are inaccessible for other users
                        os.mkdir(path, mode=0o700)
                    except:
                        print ('Could not create directory', path)
                        success = False
                        break
                else:
                    print ('Directory does not exist:', path)
                    success = False
                    break
            os.environ[e] = path
        if success:
            break

    print('Using ops and log directories', os.environ['OPSDIR'], os.environ['LOGDIR'])
    if 'RUNDIR' not in os.environ:
        os.environ['RUNDIR'] = os.environ['OPSDIR']

    # Look for the configuration
    confdir = os.environ.get('CONFDIR', None)
    if not confdir:
        for confdir in [os.environ['HOME']+'/etc/%s'%args.project, '/etc/%s'%args.project, None]:
            if not confdir:
                raise RuntimeError( 'Could not find a configuration for project %s'% args.project )
            logging.debug('Testing confdir %s'%confdir)
            if os.path.exists(confdir):
                break

    # Load the configuration
    from admingen import config
    config.set_configdir(confdir)

    # Load the project as a library
    mod = importlib.import_module(args.project)

    # Make the project directory the current directory
    print ('Moving to directory', proj_dir)
    os.chdir(proj_dir)

    # Run the project
    print ('Starting project', args.project)
    mod.run()