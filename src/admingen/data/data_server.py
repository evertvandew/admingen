""" A simple data server based on Flask.

This data will be stored directly in the file system as JSON files.
"""

import os, os.path
import json
import flask
import functools
import logging
from dataclasses import is_dataclass, asdict
from werkzeug.exceptions import BadRequest, NotFound
from admingen.data.file_db import (FileDatabase, serialiseDataclass, deserialiseDataclass, the_db,
                                   serialiseDataclasses, filter_context, multi_sort, do_leftjoin)

# Define the key for the data element that is added to indicate limited queries have reached the end
IS_FINAL_KEY = '__is_last_record'


root_path = os.getcwd()
db = None


def mk_response(reply):
    response = flask.make_response(flask.jsonify(reply))
    return response


def read_records(fullpath, cls=None, raw=False):
    """ Reads all records in a table and returns them as dictionaries. """
    # TODO: Make me return record objects instead of dictionaries.
    if fullpath[0] != '/':
        fullpath = os.path.join(root_path, fullpath)

    # We need to make an object of the whole contents of a directory
    entries = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
    
    if cls:
        data = [deserialiseDataclass(cls, open(os.path.join(fullpath, str(e))).read()) for e in entries]
        # The User table is treated differently: the password is set to asterixes.
        if fullpath.endswith('User') and not raw:
            for d in data:
                d.password = '****'
    else:
        data = [json.load(open(os.path.join(fullpath, str(e)))) for e in entries]
        # The User table is treated differently: the password is set to asterixes.
        if fullpath.endswith('User') and not raw:
            for d in data:
                d['password'] = '****'
    return data

def read_records_asdict(fullpath: str, cls=None):
    data = read_records(fullpath, cls)
    return {d['id']: d for d in data}


def mk_fullpath(path):
    offset = os.getcwd() + '/data'
    if '.' in os.path.basename(path):
        raise BadRequest("Path must be absolute.")
    fullpath = os.path.join(offset, path)
    if not os.path.exists(fullpath):
        raise NotFound(path)
    return fullpath


def get_request_data():
    if flask.request.data:
        encoding = flask.request.args.get('encoding')
        if encoding == 'base64':
            new_data = flask.request.data.decode('base64')
        else:
            new_data = flask.request.data
    else:
        # The data is encoded as form data. Just save them as JSON
        new_data = flask.request.values.to_dict()
    return new_data


def update_record(tablecls, index, db, data, update=True, mk_response=True):
    """ Flask handler for put requests """
    # Check we have either JSON or form-encoded data
    if not (flask.request.values or flask.request.is_json):
        logging.info("Client tried to post without any data")
        raise BadRequest('Inproper request')

    # Update with the new data
    if 'id' not in data:
        data['id'] = index
    if update:
        # re-use the existing data
        record = db.update(tablecls, data)
    else:
        # Overwrite existing data
        record = tablecls(**data)
        db.set(record)

    if mk_response:
        return flask.make_response(serialiseDataclass(record), 201)
    return record


def add_record(table, tablecls, data, mk_response=True):
    fullpath = mk_fullpath(table)


    # There is no ID field, create one.
    ids = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
    my_id = max(ids) + 1 if ids else 1
    data['id'] = my_id
    fullpath = f'{fullpath}/{my_id}'
    print('Created ID', str(my_id))

    data_obj = tablecls(**data)
    data_str = serialiseDataclass(data_obj)
    with open(fullpath, "w") as dest_file:
        dest_file.write(data_str)
    if mk_response:
        return flask.make_response(data_str, 201)
    return data_str


def add_handlers(app, context):
    """ This function creates and installs a number of flask handlers. """
    db = context['the_db']
    table_classes = {t.__name__: t for t in context['tables']}

    # First define some helper functions.

    @app.route('/data/<path:table>', methods=['GET'])
    def get_table(table):
        if not table:
            return
        tablecls = table_classes[table]
        data = db.query(tablecls)
        # For the User class, replace the password with asterixes.
        if table == 'User':
            for d in data:
                d.password = '****'
        # Check if the foreignkeys need to be resolved
        if 'resolve_fk' in flask.request.args:
            fks = tablecls.get_fks()
            for record in data:
                for key, t in fks.items():
                    referenced = db.get(t, getattr(record, key))
                    setattr(record, key, referenced)
        # First perform any joins
        if 'join' in flask.request.args:
            other_table, condition = flask.request.args['join'].split(',', maxsplit=1)
            data_other = read_records(mk_fullpath(other_table))
            data = do_leftjoin(table, other_table, data, data_other, condition)
    
        # Apply the filter
        if 'filter' in flask.request.args:
            def func(item, condition):
                d = asdict(item) if is_dataclass(item) else item
                try:
                    return bool(eval(condition, filter_context, d))
                except:
                    logging.error(f"Error in evaluating {condition} with variables {d}")
                    raise
        
            condition = flask.request.args['filter']
            data = [item for item in data if func(item, condition)]
        
        # Sort the results
        if 'sort' in flask.request.args:
            data = multi_sort(flask.request.args['sort'], data)
        
        # Apply limit and offset
        is_final = True
        if 'limit' in flask.request.args:
            offset = int(flask.request.args.get('offset', 0))
            limit = int(flask.request.args['limit'])
            is_final = len(data) < offset+limit
            data = data[offset:offset+limit]

        # Check for the single argument
        if flask.request.args.get('single', False):
            if len(data) != 1:
                raise BadRequest('Did not found just one single element')
            data = data[0]
            res = flask.make_response(serialiseDataclass(data))
        else:
            # Prepare the response
            res = flask.make_response(serialiseDataclasses(data))
    
        res.headers['Content-Type'] = 'application/json; charset=utf-8'
        return res

    @app.route('/data/<path:table>/<int:index>', methods=['GET'])
    def get_item(table, index):
        data = db.get(table_classes[table], index)
        # For the User records, set the password to asterixes
        if table == 'User':
            data.password = '****'
        res = flask.make_response(serialiseDataclass(data))
        res.headers['Content-Type'] = 'application/json; charset=utf-8'
        return res

    @app.route('/data/<path:table>/<int:index>', methods=['POST', 'PUT'])
    def put_item(table, index):
        """ Flask handler for put requests """
        tablecls = table_classes[table]
        data = get_request_data()
        return update_record(tablecls, index, db, data, flask.request.method == 'POST')

    @app.route('/data/<path:table>/<int:index>', methods=['DELETE'])
    def delete_item(table, index):
        tablecls = table_classes[table]
        db.delete(tablecls, index)
        return flask.make_response('', 204)

    @app.route('/data/<path:table>', methods=['POST', 'PUT'])
    def add(table):
        tablecls = table_classes[table]
        data = get_request_data()
        return add_record(table, tablecls, data)

    print('Loaded data server')


def test_multi_sort():
    d1 = [{'a': 1, 'b': 5}, {'a':2, 'b': 4}, {'a':3, 'b': 3}, {'a':3, 'b':4},
          {'a':3, 'b':2}, {'a':4, 'b':2}, {'a':5, 'b':1}]
    d2 = multi_sort('a:desc,b', d1)
    print(d2)


if __name__ == '__main__':
    test_multi_sort()
