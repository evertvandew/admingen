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

import os
import filecache
import admingen.magick as magic
import re
import json

root_path = None

def set_root(path):
    global root_path
    root_path = path

def validate_ranges(ranges, content_length):
    return all([int(r[0]) <= int(r[1]) for r in ranges]) and all([int(x) < content_length for subrange in ranges for x in subrange])


def my_get_mime(path):
    """ Get the mime type of a file. """
    mime = None
    if path.endswith('.css'):
        return 'text/css'
    
    mime = magic.from_file(path, mime=True)
    
    if mime is None:
        mime = 'application/octet-stream'
    else:
        mime = mime.replace(' [ [', '')
    return mime

def read_records(fullpath):
    # We need to make an object of the whole contents of a directory
    entries = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
    data = {int(e): json.load(open(os.path.join(fullpath, str(e)))) for e in entries}
    return data


def mk_fullpath(path):
    return '/'.join([root_path, path])


def mk_response(reply):
    response = flask.make_response(flask.jsonify(reply))
    return response


def get(path):
    """ Flask handler for get requests. """
    path_components = path.split('/')
    if '.' in path_components or '..' in path_components:
        return flask.make_response("Path must be absolute.", 400)

    fullpath = mk_fullpath(path)

    if os.path.isdir(fullpath) and path_components[0] != 'data':
        fullpath += '/index.html'

    if os.path.exists(fullpath):
        if flask.request.args.get('stat') is not None:
            mime = my_get_mime(fullpath)
    
            stat = os.stat(fullpath)
            st = {'file' : os.path.basename(fullpath),
                  'path' : '/%s' % path,
                  'access_time' : int(stat.st_atime),
                  'modification_time' : int(stat.st_mtime),
                  'change_time' : int(stat.st_ctime),
                  'mimetype' : mime}
            if not os.path.isdir(fullpath):
                st['size'] = int(stat.st_size)
            res = flask.make_response(json.dumps(st))
            res.headers['Content-Type'] = 'application/json; charset=utf-8'
            return res

        if os.path.isdir(fullpath):
            if path_components[0] == 'data':
                data = read_records(fullpath)
                res = flask.make_response(json.dumps(data))
            else:
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
    else:
        return flask.make_response('/%s: No such file or directory.' % path, 404)

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
    
    # Determine the data
    if flask.request.data:
        encoding = flask.request.args.get('encoding')
        if encoding == 'base64':
            data = flask.request.data.decode('base64')
        else:
            data = flask.request.data
    else:
        # The data is encoded as form data. Just save them as JSON
        data = json.dumps(flask.request.values.to_dict())

    # Check if the id number needs to be determined
    if not path_components[-1].isnumeric():
        if 'id' in data:
            my_id = data['id']
        else:
            # There is no ID field, create one.
            ids = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
            my_id = max(ids)+1 if ids else 1
            
        fullpath = '/'.join([fullpath, str(my_id)])
        print ('Created ID', str(my_id))

    if not flask.request.data and not flask.request.values:
        os.mkdir(fullpath)
        return flask.make_response('', 201)

    print ('Saving', fullpath)
    with open(fullpath, "w") as dest_file:
        dest_file.write(data)
    return flask.make_response('', 201)


def delete(path):
    """ Flask handler for delete requests. """
    path_components = path.split('/')
    if '.' in path_components or '..' in path_components:
        return flask.make_response("Path must be absolute.", 400)

    fullpath = '%s/%s' % (root_path, path)
    if os.path.exists(fullpath):
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
    else:
        return flask.make_response('/%s: No such file or directory.' % path, 404)

def add_handlers(app):
    getter = app.route('/<path:path>', methods=['GET', 'HEAD'])(get)
    app.route('/', defaults={'path': ''}, methods=['GET', 'HEAD'])(getter)
    app.route('/<path:path>', methods=['PUT', 'POST'])(put)
    app.route('/<path:path>', methods=['DELETE'])(delete)
