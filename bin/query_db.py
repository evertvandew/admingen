#!/usr/bin/env python3
# Script that interacts with a database

import sys
import argparse
import os, os.path

from decimal import Decimal
from datetime import datetime, date
from urllib.parse import urlparse
from admingen.data import CsvReader, mkDecimal, mkdate, mkdatetime
from pony import orm



def create_table(db, name, cols):
    names = cols[0]
    types = cols[1]
    types = [datetime if t==mkdatetime else date if t == mkdate else Decimal if t == mkDecimal else t
             for t in types]
    cols = {n: orm.Optional(t) for n, t in zip(names, types) if n != 'id'}
    table = type(name, (db.Entity,), cols)
    return table


def create_db(url, scheme, create):
    # We only want simple DB actions,
    # OK to use ponyorm.
    db = orm.Database()
    details= urlparse(url)
    print ('Create:', create)
    assert details.scheme in ['sqlite']
    if details.scheme == 'sqlite':
        path = os.path.join(os.getcwd(), details.netloc) or details.path
        print ('Creating database in', path, os.getcwd())
        db.bind(provider=details.scheme, filename=path, create_db=create)

    # Generate the data classes
    tables = {t:create_table(db, t, cols) for t, cols in scheme.items()}


    db.generate_mapping(create_tables=create)

    return db, tables
    

if __name__ == '__main__':
    parse = argparse.ArgumentParser(description='Interact with database')
    parse.add_argument('url', help='URL to the database. E.g. sqlite:///afile.db')
    parse.add_argument('--insert', help='Insert the data from stdin into the database', action='store_true')
    parse.add_argument('--scheme', help='File defining the database scheme')
    parse.add_argument('--create', help='Create the database tables', action='store_true')
    
    args = parse.parse_args()
    
    instream = sys.stdin
    
    data = CsvReader(instream)
    
    scheme = args.scheme or data.__annotations__
    db, tables = create_db(args.url, scheme, args.create)

    objects = []
    with orm.db_session():
        for table, table_data in data.items():
            t = tables[table]
            if isinstance(table_data, dict):
                table_data = table_data.values()
            objects.extend([t(**d.__dict__) for d in table_data])
