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

def create_app(args):
    if args.root_path is not None:
        root_path = args.root_path
    else:
        root_path = os.getcwd()
    set_root(root_path)

    app = flask.Flask(__name__)


    context = {}

    add_handlers(app)

    if args.datamodel:
        mod_name = os.path.basename(args.datamodel).split('.')[0]
        spec = importlib.util.spec_from_file_location(mod_name, args.datamodel)
        new_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(new_mod)

        databases = {k: file_db.FileDatabase(new_mod.database_urls[k], tables)
                     for k, tables in new_mod.all_tables.items()}

        context['databases'] = databases
        context['data_model'] = new_mod

    for m in args.filename:
        mod_name = os.path.basename(m).split('.')[0]
        new_mod = sys.modules.get(mod_name, None)
        if new_mod is None:
            spec = importlib.util.spec_from_file_location(mod_name, m)
            new_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(new_mod)

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
