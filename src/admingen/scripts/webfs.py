#!/usr/bin/env python3
""" A simple flask-website container.

Imports one standard module that implements a simple web filesystem server,
optionally add other modules as command-line options.
"""
import os
import sys
import flask
import importlib.util
from argparse import ArgumentParser

from admingen.webfs import add_handlers, set_root
from admingen.data import file_db


admingen_home = os.path.abspath(os.path.dirname(__file__) + '/../..')

def find_file(fname, search_path) -> str:
    for p in search_path:
        long_name = os.path.abspath(os.path.join(p, fname))
        print(f'Long name: {long_name}')
        if os.path.exists(long_name):
            return os.path.relpath(long_name)
    assert False, f"Module {fname} could not be found in the search path"

def create_app(args):
    if args.root_path is not None:
        root_path = args.root_path
    else:
        root_path = os.getcwd()
    set_root(root_path)

    app = flask.Flask(__name__)


    context = {}

    add_handlers(app)

    search_path = [os.getcwd(), admingen_home]

    if args.datamodel:
        mod_name = os.path.basename(args.datamodel).split('.')[0]
        fname = find_file(args.datamodel, search_path)
        spec = importlib.util.spec_from_file_location(mod_name, fname)
        new_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(new_mod)

        databases = {k: file_db.FileDatabase(new_mod.database_urls[k], tables)
                     for k, tables in new_mod.all_tables.items()}

        context['databases'] = databases
        context['datamodel'] = new_mod.all_tables
        context['database_urls'] = new_mod.database_urls

    for m in args.filename:
        if os.path.sep in m or m.endswith('.py'):
            mod_name = os.path.basename(m).split('.')[0]
            fname = find_file(m, search_path)
            print(f'Loading module from {fname}')
            spec = importlib.util.spec_from_file_location(mod_name, fname)
            print(f'Parent: {spec.parent}')
            new_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(new_mod)
        else:
            importlib.import_module(m)
            new_mod = sys.modules.get(m, None)
        new_mod.add_handlers(app, context)
    return app

def run():
    parser = ArgumentParser()
    parser.add_argument('--root-path', dest='root_path', action='store', help='Path to serve.')
    parser.add_argument('-d', '--debug', dest='debug', action='store_true',
                        help='Run in debug mode.')
    parser.add_argument('host', action='store', nargs='?', help='Host to bind to.')
    parser.add_argument('port', action='store', type=int, nargs='?', help='Port to listen on.')
    parser.add_argument('--filename', '-f', nargs='*', default=[],
                        help='One or more modules that are loaded as part of the web application')
    parser.add_argument('--datamodel', default=None)

    args = parser.parse_args()

    print('cwd:', os.getcwd())
    print('pythonpath:', os.environ.get('PYTHONPATH', ''))

    app = create_app(args)

    app.run(threaded=True, host='0.0.0.0', port=args.port, debug=args.debug)

if __name__ == '__main__':
    run()
