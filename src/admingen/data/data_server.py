""" A simple data server based on Flask.

This data will be stored directly in the file system as JSON files.
"""

import os, os.path
import json
import flask
import operator
import functools
from urllib.parse import unquote
from werkzeug.exceptions import BadRequest, NotFound
from admingen.data.file_db import (FileDatabase, serialiseDataclass, deserialiseDataclass, the_db,
                                   serialiseDataclasses)

# Define the key for the data element that is added to indicate limited queries have reached the end
IS_FINAL_KEY = '__is_last_record'


root_path = os.getcwd()

filter_context = {
    'isIn': operator.contains,
    'isTrue': lambda x: x.lower()=='true',
    'isFalse': lambda x: x.lower()!='true',
    'l_and': operator.and_,
    'eq': operator.eq,
    'neq': operator.ne,
    'lt': operator.lt,
    'gt': operator.gt,
    'le': operator.le,
    'ge': operator.ge
}


def mk_response(reply):
    response = flask.make_response(flask.jsonify(reply))
    return response


def read_records(fullpath, as_dict=False):
    """ Reads all records in a table and returns them as dictionaries. """
    # TODO: Make me return record objects instead of dictionaries.
    if fullpath[0] != '/':
        fullpath = os.path.join(root_path, fullpath)

    # We need to make an object of the whole contents of a directory
    entries = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
    data = [json.load(open(os.path.join(fullpath, str(e)))) for e in entries]
    if as_dict:
        data = {d['id']: d for d in data}
    return data


def multi_sort(descriptor, data):
    """ A function to sort a list of data (dictionaries).
        The sort descriptor is a comma-separated string of keys into the dicts.
        Optionally, the key is followed by the word ":desc", for example
            "a,b:desc,c"
    """
    sorts = descriptor.split(',')
    
    def sort_predicate(it1, it2):
        for key in sorts:
            sort_desc = False
            sort_desc = key.endswith(':desc')
            if sort_desc:
                key = key.split(':')[0]
            # Retrieve the values to be sorted on now.
            v1, v2 = [i[key] for i in [it1, it2]]
            # Do the actual comparison
            if sort_desc:
                result = (v2 > v1) - (v2 < v1)
            else:
                result = (v1 > v2) - (v1 < v2)
            # If there is a difference based on the current key, return the value
            if result != 0:
                return result
        # There was no difference in any of the keys, return 0.
        return 0
    
    return sorted(data, key=functools.cmp_to_key(sort_predicate))


def add_handlers(app, context):
    """ This function creates and installs a number of flask handlers. """
    offset = os.getcwd() + '/data'
    
    db = context['the_db']
    table_classes = {t.__name__: t for t in context['tables']}

    # First define some helper functions.
    def mk_fullpath(path):
        if '.' in os.path.basename(path):
            raise BadRequest("Path must be absolute.")
        fullpath = os.path.join(offset, path)
        if not os.path.exists(fullpath):
            raise NotFound(path)
        return fullpath

    def do_leftjoin(tabl1, tabl2, data1, data2, condition):
        condition = unquote(condition)
        # Make the association.
        results = []
        for d1 in data1:
            def eval_cond(d2):
                """ Function returns true if d2 is to be joined to d1 """
                local_context = {tabl1: d1, tabl2: d2}
                local_context.update(d2)
                local_context.update(d1)
                return bool(eval(condition, filter_context, local_context))
        
            d2s = list(filter(eval_cond, data2))
            assert len(d2s) <= 1, "Join condition %s didn't result in a unique match" % condition
            result = {}
            if d2s:
                result.update(d2s[0])
                result[tabl2] = d2s[0]
            result[tabl1] = d1
            result.update(d1)
            results.append(result)
        return results
    
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
        

    @app.route('/data/<path:table>', methods=['GET'])
    def get_table(table):
        if not table:
            return
        tablecls = table_classes[table]
        data = db.query(tablecls)
        # Check if the foreignkeys need to be resolved
        if 'resolve_fk' in flask.request.args:
            # TODO: Look for all foreign keys in the dataset, and fill in the data like a join
            pass
        # First perform any joins
        if 'join' in flask.request.args:
            other_table, condition = flask.request.args['join'].split(',', maxsplit=1)
            data_other = read_records(mk_fullpath(other_table))
            data = do_leftjoin(tabel, other_table, data, data_other, condition)
    
        # Apply the filter
        if 'filter' in flask.request.args:
            def func(item, condition):
                return bool(eval(condition, filter_context, item.__dict__))
        
            condition = flask.request.args['filter']
            data = [item for item in data if func(item, condition)]
        
        # Sort the results
        if 'sort' in flask.request.args:
            data = multi_sort(flask.request.args['sort'], data)
        
        # Apply limit and offset
        if 'limit' in flask.request.args:
            offset = int(flask.request.args.get('offset', 0))
            limit = int(flask.request.args['limit'])
            is_final = len(data) < offset+limit
            data = data[offset:offset+limit]
            if data:
                data[-1][IS_FINAL_KEY] = is_final

        # Prepare the response
        res = flask.make_response(serialiseDataclasses(data))
    
        res.headers['Content-Type'] = 'application/json; charset=utf-8'
        return res

    @app.route('/data/<path:table>/<int:index>', methods=['GET'])
    def get_item(table, index):
        res = flask.make_response(serialiseDataclass(db.get(table_classes[table], index)))
        res.headers['Content-Type'] = 'application/json; charset=utf-8'
        return res

    @app.route('/data/<path:table>/<int:index>', methods=['POST', 'PUT'])
    def put_item(table, index):
        """ Flask handler for put requests """
        tablecls = table_classes[table]
        # Check we have either JSON or form-encoded data
        if not (flask.request.values or flask.request.is_json()):
            raise BadRequest('Inproper request')
    
        # Update with the new data
        data = get_request_data()
        if 'id' not in data:
            data['id'] = index
        if flask.request.method == 'POST':
            # re-use the existing data
            record = db.update(tablecls, data)
        else:
            # Overwrite existing data
            record = tablecls(**data)
            db.set(record)

        return flask.make_response(serialiseDataclass(record), 201)


    @app.route('/data/<path:table>/<int:index>', methods=['DELETE'])
    def delete_item(table, index):
        tablecls = table_classes[table]
        db.delete(tablecls, index)
        return flask.make_response('', 204)

    @app.route('/data/<path:table>', methods=['POST', 'PUT'])
    def add(table):
        fullpath = mk_fullpath(table)

        data = get_request_data()

        # There is no ID field, create one.
        ids = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
        my_id = max(ids) + 1 if ids else 1
        data['id'] = my_id
        fullpath = f'{fullpath}/{my_id}'
        print('Created ID', str(my_id))

        data_str = json.dumps(data)
        with open(fullpath, "w") as dest_file:
            dest_file.write(data_str)
        return flask.make_response(data_str, 201)

    print('Loaded data server')


def test_multi_sort():
    d1 = [{'a': 1, 'b': 5}, {'a':2, 'b': 4}, {'a':3, 'b': 3}, {'a':3, 'b':4},
          {'a':3, 'b':2}, {'a':4, 'b':2}, {'a':5, 'b':1}]
    d2 = multi_sort('a:desc,b', d1)
    print(d2)


if __name__ == '__main__':
    test_multi_sort()
