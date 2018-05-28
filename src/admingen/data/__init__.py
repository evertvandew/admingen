

import typing
from decimal import Decimal
from datetime import date, datetime, timedelta
from admingen.util import isoweekno2day
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

def mkDecimal(s):
    return Decimal(s)


def mkdate(s):
    ''' Assume the format YYYY-MM-DD '''
    return date.strftime('%Y-%m-%d')


def mkdatetime(s):
    ''' Assume the format YYYY-MM-DD HH:MM:SS '''
    return datetime.strftime('%Y-%m-%d %H:%M:%S')


supported_types = {'str': str,
                   'decimal': mkDecimal,
                   'date': mkdate,
                   'datetime': mkdatetime,
                   'int': int,
                   'float': float
                   }


def read_tablename(stream):
    for line in stream:
        name = line.strip()
        if name:
            yield name
    return

def read_header(stream, delimiter):
    for line in stream:
        if line:
            parts = line.strip().split(delimiter)
            header_types = [p.split(':') for p in parts]
            headers = [p[0] for p in header_types]
            types = [p[1] if len(p)==2 else 'str' for p in header_types]
            types = [supported_types[t] for t in types]
            return headers, types

class dataline:
    pass


def read_lines(stream, headers, types, delimiter):
    for line in stream:
        line = line.strip()
        if not line:
            return
        parts = line.split(delimiter)
        result = dataline()
        for h, t, p in zip(headers, types, parts):
            try:
                setattr(result, h, t(p))
            except:
                msg = 'Error when converting parameter %s value %s to %s'
                raise RuntimeError(msg%(h, p, t.__name__))
        yield result


def read_lines_id(stream, headers, types, delimiter):
    return {d.id:d for d in read_lines(stream, headers, types, delimiter)}


def CsvReader(stream: typing.TextIO, delimiter=';'):
    collection = {}
    for table in read_tablename(stream):
        headers, types = read_header(stream, delimiter)
        if 'id' in headers:
            collection[table] = read_lines_id(stream, headers, types, delimiter)
        else:
            collection[table] = list(read_lines(stream, headers, types, delimiter))
    return collection


def filter(instream: typing.TextIO, script: str, outstream: typing.TextIO):
    data = CsvReader(instream)

    if isinstance(script, str):
        result = exec(script, globals(), data)
    elif callable(script):
        result = script(**data)

    dump(result, outstream)