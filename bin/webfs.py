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

from flask import Flask, request, current_app, stream_with_context, Response
from argparse import ArgumentParser

import os
import sys
import flask
import filecache
import admingen.magick as magic
import re
import json

app = Flask(__name__)
root_path = os.getcwd()

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


@app.route('/', defaults={'path': ''}, methods=['GET', 'HEAD'])
@app.route('/<path:path>', methods=['GET', 'HEAD'])
def get(path):
    path_components = path.split('/')
    if '.' in path_components or '..' in path_components:
        return flask.make_response("Path must be absolute.", 400)

    fullpath = '%s/%s' % (root_path, path)

    if os.path.isdir(fullpath) and path_components[0] != 'data':
        fullpath += '/index.html'

    if os.path.exists(fullpath):
        if (request.args.get('stat') is not None):
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
                # We need to make an object of the whole contents of a directory
                entries = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
                data = {e: json.load(open(os.path.join(fullpath, str(e)))) for e in entries}
                res = flask.make_response(json.dumps(data))
            else:
                res = flask.make_response(json.dumps(os.listdir(fullpath)))

            res.headers['Content-Type'] = 'application/json; charset=utf-8'
            return res
        else:
            stat = os.stat(fullpath)
            f = filecache.open_file(fullpath)
            r = request.headers.get('Range')
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
                res = Response(stream_with_context(stream_data()), 200, mimetype=mime, direct_passthrough=True)
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


                    res = Response(stream_with_context(stream_data()), 206, mimetype=mime, direct_passthrough=True)
                    res.headers['Content-Length'] = content_length
                    res.headers['Content-Range'] = 'bytes %s-%s/%d' % (ranges[0][0], ranges[0][1], stat.st_size)
                else:
                    res = flask.make_response('', 416)
            # res.headers['Accept-Ranges'] = 'bytes'
            return res
    else:
        return flask.make_response('/%s: No such file or directory.' % path, 404)

@app.route('/<path:path>', methods=['PUT', 'POST'])
def put(path):
    path_components = path.split('/')
    if '.' in path_components or '..' in path_components:
        return flask.make_response("Path must be absolute.", 400)

    fullpath = '%s/%s' % (root_path, path)
    
    # Do not accept writes outside the data area
    if not path_components[0] == 'data':
        return flask.make_response('/%s: File exists.' % path, 403)
    
    # Check we have either JSON or form-encoded data
    if not (request.values or request.is_json()):
        return flask.make_response('/%s: Inproper request.' % path, 400)
    
    # Determine the data
    if request.data:
        encoding = request.args.get('encoding')
        if encoding == 'base64':
            data = request.data.decode('base64')
        else:
            data = request.data
    else:
        # The data is encoded as form data. Just save them as JSON
        data = json.dumps(request.values.to_dict())

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

    if not request.data and not request.values:
        os.mkdir(fullpath)
        return flask.make_response('', 201)

    print ('Saving', fullpath)
    with open(fullpath, "w") as dest_file:
        dest_file.write(data)
    return flask.make_response('', 201)

@app.route('/<path:path>', methods=['DELETE'])
def delete(path):
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
    

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--root-path', dest='root_path', action='store', help='Path to serve.')
    parser.add_argument('-d', '--debug', dest='debug', action='store_true', help='Run in debug mode.')
    parser.add_argument('host', action='store', nargs='?', help='Host to bind to.')
    parser.add_argument('port', action='store', type=int, nargs='?', help='Port to listen on.')

    args = parser.parse_args()

    if args.root_path is not None:
        root_path = args.root_path

    app.run(threaded=True, host=args.host, port=args.port, debug=args.debug)

