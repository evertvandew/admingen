
import sys
from urllib.parse import urlparse
import typing
from decimal import Decimal
from datetime import date, datetime, timedelta
import logging
from admingen.util import isoweekno2day
from yaml import load, dump
from collections.abc import Mapping

import json
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

def mkDecimal(s='0'):
    return Decimal(s)


def mkdate(s):
    ''' Assume the format YYYY-MM-DD '''
    return date.strftime('%Y-%m-%d')


def mkdatetime(s):
    ''' Assume the format YYYY-MM-DD HH:MM:SS '''
    return datetime.strftime('%Y-%m-%d %H:%M:%S')


def id_type(s):
    return int(s)


def json_loads(s):
    return json.loads(s)



class dataset:
    def __init__(self, iterator, index=None):
        if index:
            self.data = {getattr(g, index):g for g in iterator}
        else:
            self.data = {i: g for i, g in enumerate(iterator)}

    def __getitem__(self, key):
        return self.data[key]

    def __iter__(self):
        return iter(self.data.values())

    def enrich(self, func=None, **kwargs):
        for r in self.data.values():
            if callable(func):
                update = func(r)
                r.__dict__.update(update)
            else:
                for key, getter in kwargs.items():
                    setattr(r, key, getter(r))
        return self

    def enrich_condition(self, condition, true=None, false=None):
        for r in self.data.values():
            update = {}
            if condition(r):
                if callable(true):
                    update = true(r)
                elif isinstance(true, dict):
                    update = true
            else:
                if callable(false):
                    update = false(r)
                elif isinstance(false, dict):
                    update = false
            for key, value in update.items():
                setattr(r, key, value)
        print ('Done')

    def join(self, getter, getupdate, defaults):
        for r in self.data.values():
            try:
                other = getter(r)
            except KeyError:
                # No match was made...
                other = None
            if other:
                update = getupdate(r, other)
            else:
                update = {}
            if defaults:
                for k, v in defaults.items():
                    value = update.setdefault(k, v)
                    setattr(r, k, value)
        return self


supported_types = {'str': str,
                   'decimal': mkDecimal,
                   'date': mkdate,
                   'datetime': mkdatetime,
                   'int': int,
                   'float': float,
                   'bool': bool,
                   'id': id_type,
                   'json': json_loads
                   }


def read_tablename(stream):
    for line in stream:
        name = line.strip()
        if name and not name.startswith('#'):
            supported_types[name] = int
            yield name
    return

def read_header(stream, delimiter):
    for line in stream:
        line = line.strip()
        if line and not line.startswith('#'):
            parts = line.strip().split(delimiter)
            header_types = [p.split(':') for p in parts]
            headers = [p[0].strip() for p in header_types]
            types = [p[1].strip() if len(p)==2 else 'str' for p in header_types]
            types = [supported_types[t] for t in types]
            return headers, types

class dataline(Mapping):
    @staticmethod
    def create_instance(headers, types, values):
        result = dataline()
        for h, t, p in zip(headers, types, values):
            try:
                setattr(result, h, t(p))
            except Exception as e:
                msg = 'Error when converting parameter %s value %s to %s'
                logging.exception('Error converting value')
                raise RuntimeError(msg%(h, p, t.__name__))
        return result

    # Implement the Mapping protocol
    def __getitem__(self, key):
        return getattr(self, key)
    def __iter__(self):
        return iter(self.__dict__)
    def __len__(self):
        return len(self.__dict__)



def read_lines(stream, headers, types, delimiter):
    for line in stream:
        line = line.strip()
        # Ignore comment lines.
        if line.startswith('#'):
            continue
        # If we see an empty line, the table is ended.
        if not line:
            return
        parts = line.split(delimiter)
        yield dataline.create_instance(headers, types, parts)


def read_lines_id(stream, headers, types, delimiter):
    id_key = 'id' if 'id' in headers else headers[types.index(id_type)]
    return {getattr(d, id_key):d for d in read_lines(stream, headers, types, delimiter)}


class AnnotatedDict(dict):
    def __init__(self, *args, **kwargs):
        self.__annotations__ = {}
        dict.__init__(self, *args, **kwargs)



def CsvReader(stream: typing.TextIO, delimiter=';'):
    if isinstance(stream, str):
        stream = open(stream)
    collection = AnnotatedDict()
    for table in read_tablename(stream):
        names, types = read_header(stream, delimiter)
        collection.__annotations__[table] = [names, types]
        if 'id' in names or id_type in types:
            collection[table] = read_lines_id(stream, names, types, delimiter)
        else:
            collection[table] = list(read_lines(stream, names, types, delimiter))
    return collection


def CsvWriter(stream: typing.TextIO, collection, delimiter=';'):
    for table, columns in collection.items():
        stream.write('%s\n'%table)

        parts = [delimiter.join(d) for d in zip(*collection.__annotations__[table])]
        stream.write('%s\n'%','.join(parts))

        for line in columns:
            stream.write('%s\n'%delimiter.join(line.values()))


def DataReader(url):
    parts = urlparse(url)
    if parts.scheme in ['', 'stream'] and parts.path=='stdin':
        return CsvReader(sys.stdin)
    if parts.scheme in ['', 'file', 'csv']:
        with open(parts.path or parts.netloc) as stream:
            return CsvReader(stream)
    raise RuntimeError('Unknown scheme %s'%parts.scheme)



def filter(instream: typing.TextIO, script: str, outstream: typing.TextIO, defines:dict):
    data = CsvReader(instream)
    data.update(defines)
    result = None

    if isinstance(script, str):
        def produce(**kwargs):
            nonlocal result
            result = kwargs
        data.update(globals())
        data['produce'] = produce
        exec(script, data)
    elif callable(script):
        result = script(**data)

    dump(result, outstream)