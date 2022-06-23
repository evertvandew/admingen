#!/usr/bin/env python3

import sys
import time
import datetime
from admingen.xml_template import processor, data_models, source_2_url_prefix
import enum

from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument('--output', '-o', default=sys.stdout)
parser.add_argument('--input', '-i', default=sys.stdin)
args = parser.parse_args()

# Extract the datamodel from the XML file.

_ = processor(istream=args.input, ostream=open('/dev/null', 'w'))

# Now write the python model file.

class_template = '''@mydataclass
class {name}(Record):
    {class_lines}
'''

enum_template = """{name} = enum_type('{name}', '{options}')
"""

lines = []
the_tables = {}

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
            t = details[0]
            if t == k:
                t = '"self"'
            elif t == 'datetime':
                t = "formatted_date('%d-%m-%Y %H:%M:%S')"
            elif t == 'date':
                t = "formatted_date('%Y-%m-%d')"
            elif t == 'time':
                t = 'time.fromisoformat'
            elif t == 'longstr':
                t = 'str'
            elif t in my_tables:
                t = t
            elif t == 'Color':
                t = 'str'
            elif t in enum_defs:
                t = t
            elif t != 'Decimal' and t[0].isupper():
                # This is a forward reference to an unknown entity...
                t = f'"{t}"'
            else:
                pass

            if len(details) > 1:
                options = ', '.join(details[1:])
                cld = f'mkColumnDetails({t}, "{options}")'
            else:
                if t[0] == '"':
                    cld = f'mkColumnDetails({t})'
                else:
                    cld = t

            cls.append(f'{name}: {cld}')
        c = class_template.format(name=k, class_lines='\n    '.join(cls))
        lines.append(c)

    the_tables[database] = my_tables

model_lines = '\n'.join(lines)
the_tables_str = '{' + ', '.join("'" + k + "'" + ': [' + ', '.join(v) + ']' for k, v in the_tables.items()) + '}'

file_template = f'''""" Generated model file for the project data structures.
This file was generated on {time.ctime()}. DO NOT CHANGE!
"""

from mimetypes import guess_type
from dataclasses import dataclass, is_dataclass, asdict
from enum import Enum
from datetime import datetime, date, time
from decimal import Decimal
import copy
import base64
from admingen.db_api import ColumnDetails, mkColumnDetails, required, unique
from admingen.data.db_api import Record

class fileblob:
    """ A data structure that lets random binary data be stored in the database.
        The data is stored in a base85 data structure.
        Also the original file name and data length are stored in the structure.
    """
    def __init__(self, x=None):
        if x:
            parts = x.split(',', maxsplit=3)
            if len(parts) < 4:
                self.fname = self.mime_type = ''
                self.data = b''
                self.length = 0
                return
            self.fname, length, self.mime_type, data = parts
            self.length = int(length)
            self.data = base64.b64decode(data)
        else:
            self.fname = self.mime_type = ''
            self.data = b''
            self.length = 0
    def __str__(self):
        return ','.join([self.fname, str(self.length), self.mime_type, base64.b64encode(self.data).decode('ascii')])
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
        if type(v) == t or v is None:
            pass
        elif v == 'null':
            v = None
        elif t == time.fromisoformat and type(v) == time:
            # Don't convert time fields that are already in the correct type.
            pass
        elif isinstance(v, Enum):
            pass
        elif is_dataclass(t):
            v = int(v)
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
        return asdict(self)

    def my_setattr(self, attr, value):
        constructor = cls.__annotations__[attr]
        v = constructor(value)
        self.__dict__[attr] = v

    def get_fks(cls):
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
    cls.get_fks = classmethod(get_fks)
    cls.get_referrers = classmethod(get_referrers)
    cls.convert_field = classmethod(convert_field)

    wrapped = dataclass(cls)

    # Replace any references to other data classes with integers
    references = [k for k, t in cls.__annotations__.items() if is_dataclass(t)]
    for k in references:
        wrapped.__annotations__[k] = int

    return wrapped


# Define some standard column types
class email(str): pass
class longstr(str): pass
class password(str): pass
class phone(str): pass
class url(str): pass
class path(str): pass
class Order(int): pass

# The actual data model.
{model_lines}

# Create a list with all data tables defined here.
all_tables = {the_tables_str}
database_urls = {repr(source_2_url_prefix)}
'''

args.output.write(file_template)
