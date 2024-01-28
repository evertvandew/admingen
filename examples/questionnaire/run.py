#!/usr/bin/env python3
""" A runner for the ondervrager questionnaires, that loads the Flask app in a way that uwsgi can use.
    Uwsgi needs the app object to be ready and available, without app.run being called.
"""

# The main app object is provided by the webfs module. The necessary extensions are added manually.
import os.path
import flask
import argparse

from admingen import webfs
from admingen.data import file_db, data_server, sqlite_db

use_sql = True

if use_sql:
    #import data_model_sql as data_model
    import data_model
else:
    import data_model

if use_sql:
    databases = {k: sqlite_db.SqliteDatabase(data_model.database_urls[k], tables, data_model.database_registries[k])
                 for k, tables in data_model.all_tables.items()}
else:
    databases = {k: file_db.FileDatabase(data_model.database_urls[k], tables)
                 for k, tables in data_model.all_tables.items()}


import my_queries


app = flask.Flask(__name__)
@app.route('/<path:chapter>/<path:path>')
def send_static_2(chapter, path):
    fname = f'html/{chapter}/{path}'
    mime_type = webfs.my_get_mime(fname)
    return flask.send_from_directory(f'html/{chapter}', path, mimetype=mime_type)

@app.route('/<path:path>')
def send_static(path):
    i = f'html/{path}/index.html'
    if os.path.exists(i):
        return flask.send_from_directory(f'html/{path}', 'index.html')
    fname = f'html/{path}'
    if os.path.exists(fname):
        mime_type = webfs.my_get_mime(fname)
        return flask.send_from_directory('html', path, mimetype=mime_type)
    return "NOT FOUND", 404

@app.route('/')
def send_index():
    return flask.send_from_directory('html', 'index.html')


class Commands:
    @staticmethod
    def run():
        """ Run the application in debug mode, as a stand-alone flask http server. """
        app.run(threaded=True, host='0.0.0.0', port=5000)

    @staticmethod
    def clean_db():
        """ Clean up the database, by removing any stale records. """


commands = [k for k in Commands.__dict__.keys() if not k.startswith('_')]

context = {'databases': databases,
           'database_urls': data_model.database_urls,
           'datamodel': data_model.all_tables}
my_queries.add_handlers(app, context)
data_server.add_handlers(app, context)


parser = argparse.ArgumentParser()
parser.add_argument('command', action='store', nargs='?', default=commands[0], help='Command to execute')
args = parser.parse_args()


if __name__ == '__main__':
    getattr(Commands, args.command)()
