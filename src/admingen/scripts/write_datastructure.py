#!/usr/bin/env python3

import sys
import time
import datetime
from admingen.xml_template import processor, data_models, source_2_url_prefix, compartiments
import enum

from argparse import ArgumentParser

def run():
    parser = ArgumentParser()
    parser.add_argument('--output', '-o', default=sys.stdout)
    parser.add_argument('--input', '-i', default=sys.stdin)
    args = parser.parse_args()

    # Extract the datamodel from the XML file.

    _ = processor(istream=args.input, ostream=open('/dev/null', 'w'), expand_templates=False)

    # Now write the python model file.

    class_template = '''@mydataclass
class {name}(Record):
    {class_lines}
'''

    enum_template = """@MyEnum
class {name}(IntEnum):
    {option_lines}
"""

    lines = []
    the_tables = {}

    for database, tables in data_models.items():
        enum_defs = {k: v for k, v in tables.items() if type(v) == enum.EnumMeta}
        class_defs = {k: v for k, v in tables.items() if not type(v) == enum.EnumMeta}

        for k, enum_def in enum_defs.items():
            option_lines = '\n    '.join(f'{t.name} = auto()' for t in enum_def)
            l = enum_template.format(name=k, option_lines=option_lines)
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
    the_tables_str = '{' + ', '.join("'"+k+"'"+': [' + ', '.join(v) + ']' for k, v in the_tables.items()) + '}'

    compartments_list = ['CompartmentDetails(' + ', '.join(f'{k}={repr(v)}' for k, v in c.items()) + ')' for c in compartiments.values()]
    compartments_txt = '{' + ', '.join(f'"{k}": {t}' for k, t in zip(compartiments.keys(), compartments_list)) + '}'

    file_template = f'''""" Generated model file for the project data structures.
This file was generated on {time.ctime()}. DO NOT CHANGE!
"""
from enum import IntEnum, auto
from typing import Tuple, Any, List
from admingen.db_api import ColumnDetails, mkColumnDetails, required, unique
from admingen.data.db_api import Record
from admingen.data.data_type_base import *

# The actual data model.
{model_lines}

# Create a list with all data tables defined here.
all_tables = {the_tables_str}
database_urls = {repr(source_2_url_prefix)}



@dataclass
class CompartmentDetails:
    compartimented_field: Tuple[str, Any]
    compartimented_cookie: str
    exceptions: List[Any]


compartiments = {compartments_txt}
'''


    args.output.write(file_template)

if __name__ == '__main__':
    run()
