
import sys
from urllib.parse import urlparse
import typing
from typing import List, Union, Dict, Any
from decimal import Decimal
from datetime import date, datetime, timedelta
import logging
import re
import codecs
from admingen.util import isoweekno2day
from yaml import load, dump
from collections.abc import Mapping
from typing import Dict
from dataclasses import is_dataclass, asdict

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
    if ':' in s and '-' in s:
        return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
    if '-' in s:
        return datetime.strptime(s, '%Y-%m-%d')
    if len(s) == 8:
        return datetime.strptime(s, '%Y%m%d')
    if 'T' in s:
        return datetime.strptime(s, '%Y%m%dT%H%M%S')
    return datetime.strptime(s, '%Y%m%d%H%M%S')

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

    def __bool__(self):
        return bool(self.data)

    def __len__(self):
        return len(self.data)

    def items(self):
        return self.data.items()

    def values(self):
        return self.data.values()

    def keys(self):
        return self.data.keys()

    def enrich(self, func=None, **kwargs):
        for r in self.data.values():
            if callable(func):
                update = func(r)
                r.__dict__.update(update)
            else:
                for key, getter in kwargs.items():
                    if callable(getter):
                        value = getter(r)
                    else:
                        value = getter
                    setattr(r, key, value)
        return self

    def enrich_condition(self, condition, true=None, false=None):
        if isinstance(condition, str):
            condition = lambda r: eval(condition, None, r.__dict__)
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
                if callable(value):
                    value = value(r)
                setattr(r, key, value)

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
                    update.setdefault(k, v)
            for k, v in update.items():
                setattr(r, k, v)
        return self

    def select(self, condition):
        """ Return a new dataset containing only selected records.
            The condition is either a callable, or a string containing a Python expression.
            In the Python expression, both the names of data fields and global Python names
            can be used.
        """
        if isinstance(condition, str):
            condition = lambda r: eval(condition, None, r.__dict__)
        return dataset(r for r in self.data.values() if condition(r))




basic_types = {'str': str,
                   'decimal': mkDecimal,
                   'Decimal': mkDecimal,
                   'date': mkdate,
                   'datetime': mkdatetime,
                   'int': int,
                   'float': float,
                   'bool': bool,
                   'id': id_type,
                   'json': json_loads
                   }

supported_types = basic_types.copy()

supported_type_names = {v: k for k, v in supported_types.items()}

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
            #types = [supported_types[t] for t in types]
            return headers, types

class dataline(Mapping):
    @staticmethod
    def create_instance(headers, types, values):
        result = dataline()
        for h, t, p in zip(headers, types, values):
            try:
                p = p.strip()
                if t is bool:
                    value = p and p.lower()[0] in 'ty1'
                else:
                    value = t(p)
                setattr(result, h, value)
            except Exception as e:
                msg = 'Error when converting parameter %s value %s to %s'
                logging.exception('Error converting value')
                raise RuntimeError(msg%(h, p, t.__name__))
        return result

    @staticmethod
    def getConstructor(headers, types):
        pytypes = [supported_types[t] for t in types]
        def constructor(parts):
            dl = dataline.create_instance(headers, pytypes, parts)
            return dl
        return constructor

    # Implement the Mapping protocol
    def __getitem__(self, key):
        return getattr(self, key)
    def __setitem__(self, key, value):
        setattr(self, key, value)
    def __iter__(self):
        return iter(self.__dict__)
    def __len__(self):
        return len(self.__dict__)
    def values(self):
        return self.__dict__.values()
    def __str__(self):
        return str(self.__dict__)
    def __repr__(self):
        return str(self.__dict__)


def serialiseDataclass(data):
    """ Convert a dataclass to a JSON string """
    return json.dumps(asdict(data))

def deserialiseDataclass(cls, s):
    """ Read the dataclass from a JSON string """
    return cls(json.loads(s))
    
    

def read_lines(stream, headers, types, delimiter):
    constructor = dataline.getConstructor(headers, types)
    for line in stream:
        line = line.strip()
        # Ignore comment lines.
        if line.startswith('#'):
            continue
        # If we see an empty line, the table is ended.
        if not line:
            return
        parts = line.split(delimiter)
        parts = [p.strip('"') for p in parts]
        yield constructor(parts)


def read_lines_id(stream, headers, types, delimiter):
    id_key = 'id' if 'id' in headers else headers[types.index('id')]
    return {getattr(d, id_key):d for d in read_lines(stream, headers, types, delimiter)}


class AnnotatedDict(dict):
    def __init__(self, *args, **kwargs):
        self.__annotations__ = {}
        self.__constructors__ = {}
        dict.__init__(self, *args, **kwargs)



def CsvReader(stream: typing.TextIO, delimiter=','):
    if isinstance(stream, str):
        stream = open(stream)
    collection = AnnotatedDict()
    for table in read_tablename(stream):
        names, types = read_header(stream, delimiter)
        collection.__annotations__[table] = [names, types]
        if 'id' in names or 'id' in types:
            collection[table] = read_lines_id(stream, names, types, delimiter)
        else:
            collection[table] = list(read_lines(stream, names, types, delimiter))
    return collection



quote_splitter = re.compile(r'("[^"]*")')



def mk_object_constructor(cls, types=None):
    lookup = basic_types.copy()
    if types:
        lookup.update(types)
    names, types = list(cls.__annotations__.keys()), list(cls.__annotations__.values())
    part_constructors = [(lookup[t] if t in lookup else t) for t in types]

    def constr(*parts):
        parts = [c(v) for c, v in zip(part_constructors, parts)]
        result = cls(*parts)
        return result

    return constr


####################################################################################################
## CSV character encoding scheme.
#  We use the regular encoding scheme used for C, with one additional escape sequence:
#  the delimiter is replaced with the \d escape sequence.

ESCAPE_SEQUENCE_RE = re.compile(r'''
    ( \\U........       # 8-digit hex escapes
    | \\u....           # 4-digit hex escapes
    | \\x..             # 2-digit hex escapes
    | \\[0-7]{1,3}      # Octal escapes
    | \\N\{[^}]+\}      # Unicode characters by name
    | \\[\\'"abfnrtvd]  # Single-character escapes
    )''', re.UNICODE | re.VERBOSE)

def decode_escapes(s, delimiter):
    """ Decode an encoded string """
    def decode_match(match):
        if match.group(0) == r'\d':
            return delimiter
        return codecs.decode(match.group(0), 'unicode-escape')

    return ESCAPE_SEQUENCE_RE.sub(decode_match, s)

def encode_escapes(s, delimiter):
    return codecs.encode(s, 'unicode-escape').decode('utf-8').replace(delimiter, r'\d')

def CsvTableReader(stream: typing.TextIO, targettype, delimiter=',', types=None, header=True):
    if header:
        names, types = read_header(stream, delimiter)
    constr = mk_object_constructor(targettype)
    for line in stream:
        line = line.strip()
        # Ignore comment lines.
        if line.startswith('#'):
            continue
        # If we see an empty line, the table is ended.
        if not line:
            return
        # Take care quoted parts are handled properly.
        # Split in parts without the quotes
        quoted_parts = quote_splitter.split(line)
        for i, p in enumerate(quoted_parts):
            if p.startswith('"'):
                quoted_parts[i] = p.replace(delimiter, '\d')[1:-1]
        line = ''.join(quoted_parts)

        parts = line.split(delimiter)
        # Un-escape delimiters in strings
        parts = [decode_escapes(p, delimiter) for p in parts]
        try:
            yield constr(*parts)
        except:
            logging.exception("Problem converting data from CSV file")


def getConstructor(annotation):
    if annotation in [int, str, Decimal, float]:
        return annotation.__name__
    return annotation.annotation

def CsvTableWriter(stream: typing.TextIO, records, delimiter=',', formatters=None):
    records = list(records)
    if not records:
        return
    # Write the table header
    parts = [f'{a[0]}:{getConstructor(a[1])}' for a in records[0].__annotations__.items()]
    stream.write('%s\n' % delimiter.join(parts))
    keys = list(records[0].__annotations__.keys())

    # For all dates in the records, ensure the correct format is used.
    constructors = {k:v for k, v in records[0].__annotations__.items()}
    for record in records:
        for k, constr in constructors.items():
            setattr(record, k, constr(getattr(record, k)))

    # Write the table data
    for line in records:
        parts = [getattr(line, k) for k in keys]
        # Escape special characters and the delimiter
        parts = [encode_escapes(str(p), delimiter) for p in parts]
        stream.write('%s\n' % delimiter.join(parts))


def CsvWriter(stream: typing.TextIO, collection: Dict[str, Union[List[Any], Dict[str, Any]]], delimiter=';'):
    for table, columns in collection.items():
        # Write the table name
        stream.write('%s\n'%table)

        # Write the table header
        if hasattr(collection, '__annotations__'):
            annotations = zip(*collection.__annotations__[table])
        elif is_dataclass(columns[0]):
            names = [k for k, v in columns[0].__dict__.items() if not callable(v)]
            annotations = [(k, type(v).__name__) for k, v in columns[0].__dict__.items() if not callable(v)]
            columns = [{k: getattr(c, k) for k in names} for c in columns]
        else:
            annotations = [(k, type(v).__name__) for k, v in columns[0].items()]
        parts = ['%s:%s'%(n, t) for n, t in annotations]
        stream.write('%s\n'%delimiter.join(parts))

        # Write the table data
        for line in (columns if isinstance(columns, list) else columns.values()):
            stream.write('%s\n'%delimiter.join([str(v).replace(delimiter, r'\d') for v in line.values()]))

        # Write an empty line to signal the end of the table
        stream.write('\n')


def DataReader(url):
    parts = urlparse(url)
    if parts.scheme in ['', 'stream'] and parts.path=='stdin':
        return CsvReader(sys.stdin)
    if parts.scheme in ['', 'file', 'csv']:
        with open(parts.path or parts.netloc) as stream:
            return CsvReader(stream)
    raise RuntimeError('Unknown scheme %s'%parts.scheme)



def filter(instream: typing.TextIO, script: str, outstream: typing.TextIO, defines:dict, delimiter=','):
    data = CsvReader(instream, delimiter=delimiter)
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
