#!/usr/bin/env python3

# The MIT License (MIT)
#
# Copyright (c) 2015 Charles Francoise
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import flask

import os, os.path
import filecache
import admingen.magick as magic
import re
import json
import operator
import logging

root_path = None
debug_mode = False


def set_root(path):
    global root_path
    root_path = os.path.abspath(path)

def validate_ranges(ranges, content_length):
    return all([int(r[0]) <= int(r[1]) for r in ranges]) and all([int(x) < content_length for subrange in ranges for x in subrange])


def my_get_mime(path):
    """ Get the mime type of a file. """
    mime = None
    if path.endswith('.css'):
        return 'text/css'

    if os.path.exists(path):
        mime = magic.from_file(path, mime=True)
    else:
        logging.error(f"Trying to look up mime for file {path} failed: NOT FOUND")
    
    if mime is None:
        mime = 'application/octet-stream'
    else:
        mime = mime.replace(' [ [', '')
    return mime

def read_records(fullpath):
    if fullpath[0] != '/':
        fullpath = os.path.join(root_path, fullpath)
    # We need to make an object of the whole contents of a directory
    entries = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
    data = {int(e): json.load(open(os.path.join(fullpath, str(e)))) for e in entries}
    for key, value in data.items():
        value['id'] = key
    return data


def mk_fullpath(path):
    return '/'.join([root_path, path])


def mk_response(reply):
    response = flask.make_response(flask.jsonify(reply))
    return response


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


def do_leftjoin(tabl1, tabl2, data1, data2, condition):
    # Make the association.
    results = []
    for d1 in data1.values():
        def eval_cond(d2):
            """ Function returns true if d2 is to be joined to d1 """
            local_context = {tabl1:d1, tabl2:d2}
            local_context.update(d2)
            local_context.update(d1)
            return bool(eval(condition, filter_context, local_context))
    
        d2s = list(filter(eval_cond, data2.values()))
        assert len(d2s) <= 1, "Join condition %s didn't result in a unique match"%condition
        result = d1.copy()
        result[tabl1] = d1
        if d2s:
            result.update(d2s[0])
            result[tabl2] = d2s[0]
        results.append(result)
    return results

def get_data(path, fullpath):
    if os.path.exists(fullpath):
        
        res = flask.make_response(open(fullpath).read())
        res.headers['Content-Type'] = 'application/json; charset=utf-8'
        return res

    return flask.make_response('/%s: No such file or directory.' % path, 404)


def get(path):
    """ Flask handler for get requests. """
    path_components = path.split('/')
    if '.' in path_components or '..' in path_components:
        return flask.make_response("Path must be absolute.", 400)

    fullpath = mk_fullpath(path)
    
    if path_components[0] == 'data':
        return get_data(path, fullpath)

    if os.path.isdir(fullpath):
        path += '/index.html'
        fullpath = mk_fullpath(path)
    
    if not os.path.exists(fullpath):
        return flask.make_response('/%s: No such file or directory.' % path, 404)
    

    if os.path.isdir(fullpath):
        res = flask.make_response(json.dumps(os.listdir(fullpath)))
        res.headers['Content-Type'] = 'application/json; charset=utf-8'
        return res
    else:
        stat = os.stat(fullpath)
        f = filecache.open_file(fullpath)
        r = flask.request.headers.get('Range')
        m = re.match('bytes=((\d+-\d+,)*(\d+-\d*))', r) if r is not None else None
        if r is None or m is None:
            f.seek(0)
            def stream_data():
                while True:
                    d = f.read(8192)
                    if len(d) > 0:
                        yield d
                    else:
                        break

            mime = my_get_mime(fullpath)
            res = flask.Response(flask.stream_with_context(stream_data()), 200, mimetype=mime, direct_passthrough=True)
            res.headers['Content-Length'] = stat.st_size
        else:
            ranges = [x.split('-') for x in m.group(1).split(',')]
            if validate_ranges(ranges, stat.st_size):
                content_length = 0
                for rng in ranges:
                    if rng[1] == '':
                        content_length = content_length + stat.st_size - int(rng[0]) + 1
                    else:
                        content_length = content_length + int(rng[1]) - int(rng[0]) + 1
                def stream_data():
                    for r in ranges:
                        f.seek(int(r[0]))
                        if r[1] == '':
                            while True:
                                d = f.read(8192)
                                if len(d) > 0:
                                    yield d
                                else:
                                    break
                        else:
                            for s in [min(8192, int(r[1]) - i + 1) for i in range(int(r[0]), int(r[1]), 8192)]:
                                d = f.read(s)
                                yield d

                res = flask.Response(flask.stream_with_context(flask.stream_data()), 206, mimetype=flask.mime, direct_passthrough=True)
                res.headers['Content-Length'] = content_length
                res.headers['Content-Range'] = 'bytes %s-%s/%d' % (ranges[0][0], ranges[0][1], stat.st_size)
            else:
                res = flask.make_response('', 416)
        # res.headers['Accept-Ranges'] = 'bytes'
        return res

def put(path):
    """ Flask handler for put requests """
    path_components = path.split('/')
    if '.' in path_components or '..' in path_components:
        return flask.make_response("Path must be absolute.", 400)

    fullpath = '%s/%s' % (root_path, path)
    
    # Do not accept writes outside the data area
    if not path_components[0] == 'data':
        return flask.make_response('/%s: File exists.' % path, 403)
    
    # Check we have either JSON or form-encoded data
    if not (flask.request.values or flask.request.is_json()):
        return flask.make_response('/%s: Inproper request.' % path, 400)

    # Make an initial data object for merging old and new data
    data = {}
    
    # Check if the id number needs to be determined
    if not path_components[-1].isnumeric():
        # There is no ID field, create one.
        ids = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
        my_id = max(ids) + 1 if ids else 1
        data['id'] = my_id
        fullpath = '/'.join([fullpath, str(my_id)])
        print('Created ID', str(my_id))
    elif flask.request.method == 'POST' and os.path.isfile(fullpath):
        # If this is a POST request, get any existing data
        data = json.load(open(fullpath))

    # Update with the new data
    if flask.request.data:
        encoding = flask.request.args.get('encoding')
        if encoding == 'base64':
            new_data = flask.request.data.decode('base64')
        else:
            new_data = flask.request.data
    else:
        # The data is encoded as form data. Just save them as JSON
        new_data = flask.request.values.to_dict()
    data.update(new_data)

    if not flask.request.data and not flask.request.values:
        os.mkdir(fullpath)
        return flask.make_response('', 201)

    print('Saving', fullpath, data)
    data_str = json.dumps(data)
    with open(fullpath, "w") as dest_file:
        dest_file.write(data_str)
    return flask.make_response(data_str, 201)


def delete(path):
    """ Flask handler for delete requests. """
    path_components = path.split('/')
    if '.' in path_components or '..' in path_components:
        return flask.make_response("Path must be absolute.", 400)

    fullpath = '%s/%s' % (root_path, path)
    if not os.path.exists(fullpath):
        return flask.make_response('/%s: No such file or directory.' % path, 404)

    if os.path.isdir(fullpath):
        if os.listdir(fullpath) == []:
            os.rmdir(fullpath)
            return flask.make_response('', 204)
        else:
            print(os.listdir(fullpath))
            return flask.make_response('/%s: Directory is not empty.' % path, 403)
    else:
        os.remove(fullpath)
        return flask.make_response('', 204)


def add_handlers(app):
    getter = app.route('/<path:path>', methods=['GET', 'HEAD'])(get)
    app.route('/', defaults={'path': ''}, methods=['GET', 'HEAD'])(getter)
    if debug_mode:
        app.route('/<path:path>', methods=['PUT', 'POST'])(put)
        app.route('/<path:path>', methods=['DELETE'])(delete)



def testjoin():
    # Try the following join:
    # sab_planning.WerknemerTeam?filter=l_and(eq(ploegleider,{{ploegleider}}),eq(start,{{start}}))&join=sab_planning.Werknemer,eq(werknemer,Werknemer['id'])
    data1 = read_records('WerknemerTeam')
    data2 = read_records('Werknemer')
    j = do_leftjoin('WerknemerTeam', 'Werknemer', data1, data2, condition='eq(int(werknemer),Werknemer["id"])')
    print(j)

if __name__ == '__main__':
    set_root('/home/ehwaal/projects/sab/html/data')
    testjoin()
