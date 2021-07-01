
import sys
from urllib.parse import urlparse
import typing
from typing import List, Union, Dict, Any
from decimal import Decimal
from datetime import date, datetime, timedelta
from enum import Enum
import logging
import re
import codecs
import bcrypt
import os.path
from admingen.util import isoweekno2day
from yaml import load, dump
from collections.abc import Mapping
from typing import Dict, List, Union, Type
from dataclasses import is_dataclass, asdict
from .db_api import db_api, Record

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


def enrich(values, func=None, **kwargs):
    for r in values:
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
    return values

def enrich_condition(values, condition, true=None, false=None):
    if isinstance(condition, str):
        condition = lambda r: eval(condition, None, r.__dict__)
    for r in values:
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
        enrich(self.data.values(), func, **kwargs)
        return self

    def enrich_condition(self, condition, true=None, false=None):
        enrich_condition(self.data.values(), condition, true, false)

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


def password2str(value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    salt = bcrypt.gensalt()
    hash = bcrypt.hashpw(value, salt)
    return hash

def checkpasswd(clear, hashed):
    if isinstance(clear, str):
        clear = clear.encode('utf-8')
    if isinstance(hashed, str):
        hashed = hashed.encode('utf8')
    return bcrypt.checkpw(clear, hashed)





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
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(f'{key} not found in dataitem')
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


class ExtendibleJsonEncoder(json.JSONEncoder):
    def default(self, o):
        """ We have three tricks to jsonify objects that are not normally supported by JSON.
            * Dataclass instances are serialised as dicts.
            * For objects that define a __json__ method, that method is called for serialisation.
            * For other objects, the str() protocol is used, i.e. the __str__ method is called.
        """
        if is_dataclass(o):
            result = asdict(o)
            return result
        if hasattr(o, '__json__'):
            return o.__json__()
        return str(o)

def serialiseDataclass(data):
    """ Convert a dataclass to a JSON string """
    result = json.dumps(data, cls=ExtendibleJsonEncoder)
    return result

def serialiseDataclass_old(data):
    """ Convert a dataclass to a JSON string """
    ddict = {k: str(v) for k, v in asdict(data).items()}
    return json.dumps(ddict)

def deserialiseDataclass(cls, s):
    """ Read the dataclass from a JSON string """
    ddict = json.loads(s)
    result = cls(**{k: (None if ddict[k] in [None, 'None', ''] else t(ddict[k])) for k, t in cls.__annotations__.items()
                    if k in ddict})
    return result

def serialiseDataclasses(data):
    """ Serialize a list of data items """
    # We need to convert all simple types to strings, but not lists or dictionaries.
    result = json.dumps(data, cls=ExtendibleJsonEncoder)
    return result
    

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



def CsvReader(stream: typing.TextIO, delimiter=';'):
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
        try:
            result = cls(*parts)
        except:
            print(f"Error in creating object of type {cls} with arguments {parts}", file=sys.stderr)
            raise
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


###############################################################################
## Some useful types for use in CSV files.

class enum_type:
    def __init__(self, name, options):
        self.annotation = name
        self.my_enum = Enum(name, options)
        self.my_enum.__str__ = lambda self: self.name
    def __call__(self, x):
        if type(x) == self.my_enum:
            return x
        return self.my_enum[x]
    def __getattr__(self, key):
        return self.my_enum[key]


def formatted_date(fmt):
    """ Custom converter class for dates."""
    class MyDate:
        annotation = f'formatted_date("{fmt}")'
        def __init__(self, x):
            if type(x).__name__ == 'MyDate':
                self.dt = x.dt
            else:
                self.dt = datetime.strptime(x, fmt)
            self.fmt = fmt
        def __str__(self):
            return self.dt.strftime(self.fmt)
    return MyDate


DASH = '-'

def date_or_dash(fmt):
    """ Custom converter for either a dash ('-') or a formatted date. """
    class MyDate(formatted_date(fmt)):
        annotation = f'date_or_dash("{fmt}")'
        def __init__(self, x):
            if isinstance(x, str) and x == '-':
                self.dt = DASH
            else:
                super().__init__(x)
        def __str__(self):
            if self.dt == DASH:
                return self.dt
            return self.dt.strftime(self.fmt)
    return MyDate

###############################################################################
## CSV table reader and writer.

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
        elif isinstance(columns[0], dict):
            annotations = [(k, type(v).__name__) for k, v in columns[0].items()]
        else:
            max_cols = max([len(r) for r in columns])
            annotations = [(i+1, 'str') for i in range(max_cols)]
        parts = ['%s:%s'%(n, t) for n, t in annotations]
        stream.write('%s\n'%delimiter.join(parts))

        # Write the table data
        for line in (columns if isinstance(columns, list) else columns.values()):
            values = line.values() if isinstance(line, dict) else line
            if values:
                stream.write('%s\n'%delimiter.join([str(v).replace(delimiter, r'\d').replace('\n', r'\n') for v in values]))
            else:
                # Lines can not be empty: simply write a single delimiter.
                stream.write(delimiter+'\n')

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
        #print("Calling script with settings:", data, file=sys.stderr)
        exec(script, data)
    elif callable(script):
        result = script(**data)

    dump(result, outstream)


class CsvDb(db_api):
    """ A wrapper that makes CSV database usable from the generated applications.
        The biggest issue is that the CSV db stores stuff as dicts, while the
        API works in dataclass records.
    """
    def __init__(self, fname, delimiter=','):
        self.filename = fname
        self.delimiter = delimiter
        with open(fname) as inp:
            self.data = CsvReader(inp, delimiter)

    def __del__(self):
        """ Save the database """
        self.save()

    def get(self, table: Type[Record], index: int) -> Record:
        if not isinstance(table, str):
            tablename = table.__name__
            data = self.data[tablename][index]
            return table(**data)
        raise RuntimeError("We need to know the type of the data")

    def get_many(self, table: Type[Record], indices: List[int]=None) -> List[Record]:
        indices = indices or list(self.data[table.__name__].keys())
        records = [self.get(table, i) for i in indices]
        records = [r for r in records if r]
        return records

    def add(self, table: Union[Type[Record], Record], record: Record=None) -> Record:
        if not record:
            record = table
            table = type(table).__name__
        elif not isinstance(table, str):
            table = table.__name__
        current = max(self.data[table].keys())
        record.id = current+1
        self.data[table][record.id] = asdict(record)
        self.save()
        return record

    def set(self, record: Record) -> None:
        table = type(record).__name__
        self.data[table][record.id] = asdict(record)
        return record

    def update(self, table: Union[Type[Record], dict], record: dict=None) -> None:
        if not record:
            record = table
            table = type(table).__name__
        elif not isinstance(table, str):
            table = table.__name__
        current = self.data[table][int(record['id'])]
        for k, v in record.items():
            current[k] = v
        self.save()
        return table(**current)

    def delete(self, table:Type[Record], index: int) -> None:
        if not isinstance(table, str):
            table = table.__name__
        del self.data[table][index]

    def save(self):
        with open(self.filename, 'w') as out:
            CsvWriter(out, self.data, self.delimiter)


class SplitCsvDb(db_api):
    """ Split databases in separate files. The user supplies a predicate to select
        the right database file.
    """
    def __init__(self, predicate, delimiter=',', directory='data/csv_db'):
        self.dbs = {}
        self.predicate = predicate
        self.directory = directory
        self.delimiter = delimiter

    def get_db(self):
        fname = self.predicate()
        if fname not in self.dbs:
            self.dbs[fname] = CsvDb(os.path.join(self.directory, fname), self.delimiter)
        return self.dbs[fname]

    def get(self, *args):
        return self.get_db().get(*args)
    def get_many(self, *args):
        return self.get_db().get_many(*args)
    def add(self, *args):
        return self.get_db().add(*args)
    def set(self, *args):
        return self.get_db().set(*args)
    def update(self, *args):
        return self.get_db().update(*args)
    def delete(self, *args):
        return self.get_db().delete(*args)
    def save(self, *args):
        return self.get_db().save(*args)
