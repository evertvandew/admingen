
import sys
from urllib.parse import urlparse
import typing
from decimal import Decimal
from datetime import date, datetime, timedelta
from admingen.util import isoweekno2day
from yaml import load, dump
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

class dataline:
    pass


def read_lines(stream, headers, types, delimiter):
    for line in stream:
        line = line.strip()

        # Ignore comment lines.
        if line.startswith('#'):
            continue
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


class AnnotatedDict(dict):
    def __init__(self, *args, **kwargs):
        self.__annotations__ = {}
        dict.__init__(self, *args, **kwargs)



def CsvReader(stream: typing.TextIO, delimiter=';'):
    collection = AnnotatedDict()
    for table in read_tablename(stream):
        names, types = read_header(stream, delimiter)
        collection.__annotations__[table] = [names, types]
        if 'id' in names:
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