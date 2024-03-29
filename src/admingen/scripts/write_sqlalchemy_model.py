#!/usr/bin/env python3

import sys
import time
import datetime
import re
from admingen.xml_template import processor, data_models, source_2_url_prefix
import enum

from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument('--output', '-o', default=None)
parser.add_argument('--input', '-i', default=sys.stdin)
args = parser.parse_args()


def first(iterable):
    return next(iter(iterable))



def run():
    # Extract the datamodel from the XML file.

    _ = processor(istream=args.input, ostream=open('/dev/null', 'w'))

    # Now write the python model file.

    class_template = '''@mapper_registry.mapped
@mydataclass
class {name}:
    {class_lines}
'''

    enum_template = """{name} = enum_type('{name}', '{options}')
    """

    enum_line_template = """{name}: {py_type} = field(default={default}, metadata={{"sa": Column(sq.Enum({py_type}._my_enum))}})"""
    regular_line_template = """{name}: {py_type} = field(default={default}, metadata={{"sa": Column({sa_type}{options})}})"""
    pk_line_template = """{name}: {py_type} = field(init=False, metadata={{"sa": Column({sa_type}, primary_key=True)}})"""
    fk_line_template = """{name}: int = field(default=None, metadata={{"sa": Column(Integer, ForeignKey({ft}, ondelete="{on_delete}"){options})}})"""

    lines = []
    the_tables = {}


    from_str_conversions = {'datetime': 'datetime.strptime({s}, "%d-%m-%Y %H:%M:%S")',
                       'date': 'date.strptime({s}, "%Y-%m-%d")',
                       'time': 'time.fromisoformat({s})',
                       'longstr': "str({s})",
                       'Color': 'str({s})',
                       'image': 'image({s})',
                       'password': 'str({s})',
                       'fileblob': 'fileblob({s})'
    }

    def generate_from_str(cls):
        lines = []
        for key, details in cls.items():
            value_type = details[0]
            if conversion_base := from_str_conversions.get(value_type, None):
                conversion = conversion_base.format(s=f'ddict["{key}"]')
                lines.append(f'''        ddict["{key}"] = {conversion} if ddict["{key}"] else None''')

        txt = '\n'.join(lines)
        result = f'''
    @classmethod
    def from_string(cls, string):
        # Convert a string to an instance of cls.
        # The first step is parsing the string as Json.
        ddict = json.loads(string)
        # Apply custom conversions
{txt}
        # Instantiate the cls.
        return cls(**ddict)
'''
        return result


    def generate_get_fks(cls, fks):
        txt = '{' + ', '.join(f"'{k}': {v}" for k, v in fks.items()) + '}'
        return f'''
    @classmethod
    def get_fks(cls):
        return {txt}
'''

    dmtype_2_satype = {'int': "Integer",
                       'str': "Unicode",
                       'bool': "Boolean",
                       'float': "Float",
                       'password': "String(30)",
                       'image': "FILEBLOB",
                       'longstr': "Unicode",
                       'fileblob': "FILEBLOB",
                       'decimal': "DECIMAL",
                       'datetime': 'DateTime',
                       'date': 'Date',
                       'time': 'Time',
                       'color': 'String(10)',
                       'url': 'String(2048)'
    }

    dmtype_2_pytype = {'datetime': "datetime",
                       'date': "date",
                       'time': 'time.fromisoformat',
                       'longstr': "str",
                       'Color': 'str',
                       # The following types are just the same
                       'int': "int",
                       'str': "str",
                       'float': "float",
                       'bool': "bool",
                       'image': 'image',
                       'password': 'str',
                       'fileblob': 'fileblob',
                       'color': 'Color',
                       'url': 'str'
    }

    dmtype_2_default = {'str': "''", 'longstr': "''", 'float': "0.0", 'int': "0"}

    # A default value can either be a literal (without spaces) or a quoted string
    default_matcher = re.compile(r'''default=([^'"\s]+|(?P<quote>['"])[^'"]*(?P=quote))''')


    # Find all foreign keys for all tables
    all_fks = {}
    for database, tables in data_models.items():
        class_defs = {k: v for k, v in tables.items() if not type(v) == enum.EnumMeta}
        table_fks = {}
        for table_name, cls_def in class_defs.items():
            fks = {k: v[0] for k, v in cls_def.items() if v[0] in class_defs}
            table_fks[table_name] = fks
        all_fks[database] = table_fks


    Flags = enum.Enum('Flags', 'Optional')

    for database, tables in data_models.items():
        enum_defs = {k: v for k, v in tables.items() if type(v) == enum.EnumMeta}
        class_defs = {k: v for k, v in tables.items() if not type(v) == enum.EnumMeta}

        for k, enum_def in enum_defs.items():
            l = enum_template.format(name=k, options=' '.join(t.name for t in enum_def))
            lines.append(l)

        my_tables = []
        for k, cls_def in class_defs.items():
            my_tables.append(k)
            cls = []
            for name, details in cls_def.items():
                # Skip any private or protected items.
                if name.startswith('_'):
                    continue
                raw_t = details[0]

                details_string = ','.join(details)
                options = []
                flags = set([])
                if 'optional' in details:
                    flags.add(Flags.Optional)

                default = default_matcher.search(details_string)
                if default:
                    default = default.group().split('=', maxsplit=1)[1]
                else:
                    default = dmtype_2_default.get(raw_t, None) if ('optional' not in details) else None

                if default is not None:
                    flags.add(Flags.Optional)

                if Flags.Optional in flags:
                    options.append('nullable=True')
                else:
                    options.append('nullable=False')

                if options:
                    options = ', ' + ','.join(options)
                else:
                    options = ''

                if raw_t == k:
                    cls.append(fk_line_template.format(name=name, ft=f'"{raw_t}.id"', options=options, on_delete="SET NULL"))
                elif name == 'id':
                    py_type = dmtype_2_pytype[raw_t]
                    sa_type = dmtype_2_satype[raw_t]
                    cls.append(pk_line_template.format(name=name, py_type=py_type, sa_type=sa_type, default=None))
                elif raw_t in dmtype_2_pytype:
                    py_type = dmtype_2_pytype[raw_t]
                    sa_type = dmtype_2_satype[raw_t]
                    cls.append(regular_line_template.format(name=name, py_type=py_type, sa_type=sa_type, default=default, options=options))
                elif raw_t in my_tables:
                    on_delete = "SET NULL" if Flags.Optional in flags else "CASCADE"
                    cls.append(fk_line_template.format(name=name, ft=f'"{raw_t}.id"', options=options, on_delete=on_delete))
                elif raw_t in enum_defs:
                    default = f'{first(enum_defs[raw_t])}'
                    cls.append(enum_line_template.format(name=name, py_type=raw_t, default=default))
                elif '.' in raw_t:
                    # Assume this refers to another entry in some other database. In this database it is represnted by an int.
                    cls.append(regular_line_template.format(name=name, py_type='int', sa_type='Integer', default=None, options=options))
                else:
                    assert False, f"Unknown data type {name}, {raw_t}"

            c = class_template.format(name=k, class_lines='\n    '.join(cls))
            lines.append(c)
            lines.append(generate_from_str(cls_def))
            lines.append(generate_get_fks(cls_def, all_fks[database][k]))

        the_tables[database] = my_tables

    model_lines = '\n'.join(lines)
    the_tables_str = '{' + ', '.join("'" + k + "'" + ': [' + ', '.join(v) + ']' for k, v in the_tables.items()) + '}'

    file_template = f'''""" Generated model file for the project data structures.
This file was generated on {time.ctime()}. DO NOT CHANGE!
"""

import json
from mimetypes import guess_type
from dataclasses import dataclass, is_dataclass, asdict, field
from enum import Enum
from datetime import datetime, date, time
from decimal import Decimal
import copy
import base64
import sqlalchemy.types as types
from admingen.db_api import ColumnDetails, mkColumnDetails, required, unique
from admingen.data.db_api import Record

class fileblob(bytes):
    """ A data structure that lets random binary data be stored in the database.
        The data is stored in a base85 data structure.
        Also the original file name and data length are stored in the structure.
    """
    def __init__(self, x=None):
        if x:
            parts = x.split(b',', maxsplit=3)
            if len(parts) < 4:
                self.fname = self.mime_type = ''
                self.data = b''
                self.length = 0
                return
            self.fname, length, self.mime_type = [p.decode('ascii') for p in parts[:3]]
            data = parts[3]
            self.length = int(length)
            self.data = base64.b64decode(data)
        else:
            self.fname = self.mime_type = ''
            self.data = b''
            self.length = 0
    def __str__(self):
        return ','.join([self.fname, str(self.length), self.mime_type, base64.b64encode(self.data).decode('ascii')])
    def __bytes__(self):
        return self.__str__().encode('ascii')
    def __hash__(self):
        return hash(self.data)
    def __eq__(self, other):
        return hash(self.data) == hash(other.data)
    def __bool__(self):
        return bool(self.data)
    @staticmethod
    def construct(fname, data):
        blob = fileblob()
        blob.fname = fname
        blob.data = data
        blob.length = len(data)
        blob.mime_type = guess_type(fname)[0]
        return blob

image = fileblob

class FILEBLOB(types.TypeDecorator):
    impl = types.LargeBinary
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return value.__bytes__()
    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return fileblob(value)

class enum_type:
    def __init__(self, name, options):
        self._name = name
        self._my_enum = Enum(name, options)
        self._my_enum.__str__ = lambda self: str(self.value)
    def __call__(self, x):
        if isinstance(x, int):
            return self._my_enum(x)
        if '.' in x:
            x = x.split('.')[-1]
        elif isinstance(x, str) and x.isnumeric():
            return self._my_enum(int(x))
        return self._my_enum[x]
    def __getattr__(self, key):
        if not key.startswith('_'):
            return self._my_enum[key]
        return object.__getattr(self, key)
    def __str__(self):
        return self._name
    def __len__(self):
        return len(self._my_enum)
    def __iter__(self):
        return iter(self._my_enum)

def formatted_date(fmt):
    """ Custom converter class for dates."""
    class MyDate:
        annotation = 'formatted_date("%s")' % fmt
        forward_funcs = ['__add__']
        def __init__(self, x):
            if type(x).__name__ == 'MyDate':
                self.dt = x.dt
            else:
                if x:
                    if isinstance(x, str):
                        self.dt = datetime.strptime(x, fmt)
                    elif isinstance(x, datetime):
                        self.dt = copy.copy(x)
                else:
                    self.dt = None
            self.fmt = fmt
        def __str__(self):
            if not self.dt:
                return 'None'
            return self.dt.strftime(self.fmt)

        def __add__(self, other):
            # TODO: Add appropriate converters for 'other'
            return self.dt + other

        @classmethod
        def cast_argument(cls, other):
            if isinstance(other, str):
                other = datetime.strptime(other, fmt)
            return other

        @classmethod
        def forward_func(cls, f):
            dt_func = getattr(datetime, f)
            setattr(cls, f, lambda self, *args: dt_func(self.dt, *[cls.cast_argument(a) for a in args]))

        def __cmp__(self, other):
            if isinstance(other, str):
                other = datetime.strptime(other, fmt)
            return self.dt == other

        def __lt__(self, other):
            if isinstance(other, str):
                other = datetime.strptime(other, fmt)
            return self.dt < other

        def __gt__(self, other):
            if isinstance(other, str):
                other = datetime.strptime(other, fmt)
            return self.dt > other

        def __ge__(self, other):
            return not (self < other)

        def __le__(self, other):
            return not (self > other)

        def __ne__(self, other):
            if isinstance(other, str):
                other = datetime.strptime(other, fmt)
            return self.dt != other

        def __eq__(self, other):
            return not (self != other)

    for f in MyDate.forward_funcs:
        MyDate.forward_func(f)
    return MyDate


DASH = '-'

def date_or_dash(fmt):
    """ Custom converter for either a dash ('-') or a formatted date. """
    class MyDate(formatted_date(fmt)):
        annotation = 'date_or_dash("%s")' % fmt
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


def mydataclass(cls):
    """ Returns a standard Python dataclass with one additional field: id.
        The constructor assures that the keys of the object have the correct type.
    """
    # All tables must have a primary key field.
    if 'id' not in cls.__annotations__:
        cls.__annotations__['id'] = cls

    # Replace any 'self' annotations with cls.
    for k in cls.__annotations__.keys():
        t = cls.__annotations__[k]
        if isinstance(t, str) and t == 'self':
            cls.__annotations__[k] = cls

    original_annotations = copy.copy(cls.__annotations__)
    cls.__original_annotations = original_annotations

    def convert_field(cls, key, v):
        """ Return the value in the correct type for field key. """
        assert (k in cls.__annotations__)
        t = cls.__annotations__[key]
        if t == bool and v is None:
            v = False
        if type(v) == t or v is None:
            pass
        elif isinstance(v, str) and v == 'null':
            v = None
        elif t == time.fromisoformat and type(v) == time:
            # Don't convert time fields that are already in the correct type.
            pass
        elif isinstance(v, Enum):
            v = t(str(v))
        elif is_dataclass(t):
            v = int(v)
        elif t == fileblob:
            if type(v) not in [str, bytes]:
                v = str(v)
            if isinstance(v, str):
                v = v.encode('ascii')
            v = t(v)
        else:
            print('Converting:', k, v, cls)
            if v == 'None' or not v:
                v = None
            else:
                v = t(v)
        return v

    def __init__(self, *args, **kwargs):
        data = dict(zip(cls.__annotations__, args))
        data.update(kwargs)
        for k in cls.__annotations__.keys():
            if k == 'id' and k not in data:
                continue
            v = convert_field(cls, k, data.get(k, None))
            setattr(self, k, v)

    def __json__(self):
        d = asdict(self)
        # JSON does not support bytes.
        byte_keys = [k for k, t in self.__annotations__.items() if t == fileblob]
        for k in byte_keys:
            if d[k]:
                d[k] = d[k].decode('ascii')
        return d

    def my_setattr(self, attr, value):
        constructor = cls.__annotations__[attr]
        v = constructor(value)
        self.__dict__[attr] = v

    def get_fks_old(cls):
        fks = [k for k, t in original_annotations.items() if is_dataclass(t)]
        fkts = [original_annotations[k] for k in fks]
        return dict(zip(fks, fkts))

    def get_referrers(cls):
        """ Find all table:item pairs that refer to this table """
        referrers = [(t, k) for t in all_tables for k, fkt in t.get_fks().items() if fkt is cls]
        return referrers


    cls.__init__ = __init__
    cls.__json__ = __json__
    cls.set_attr = my_setattr
    cls.get_fks_old = classmethod(get_fks_old)
    cls.get_referrers = classmethod(get_referrers)
    cls.convert_field = classmethod(convert_field)
    cls.__tablename__ = cls.__name__
    cls.__sa_dataclass_metadata_key__ = "sa"

    wrapped = dataclass(cls)

    # Replace any references to other data classes with integers
    references = [k for k, t in cls.__annotations__.items() if is_dataclass(t)]
    for k in references:
        wrapped.__annotations__[k] = int

    return wrapped

import sqlalchemy as sq
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer, String, Boolean, DateTime, Date, Unicode, Text
from sqlalchemy.orm import registry
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship


# Define some standard column types
class email(str): pass
class longstr(str): pass
class password(str): pass
class phone(str): pass
class url(str): pass
class path(str): pass
class Order(int): pass
class Color(str): pass

mapper_registry = registry()

# The actual data model.
{model_lines}

# Create a list with all data tables defined here.
all_tables = {the_tables_str}
database_urls = {repr(source_2_url_prefix)}
database_registries = {{ "{first(data_models.keys())}" : mapper_registry,
                     'reverse_lookup': {{ }} }}
'''

    assert(len(data_models) == 1)
    output = open(args.output, 'w') if args.output else sys.stdout
    output.write(file_template)

if __name__ == '__main__':
    run()
