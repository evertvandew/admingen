
import logging
import os.path
import shutil
from dataclasses import dataclass
from typing import Tuple
from urllib.parse import urlparse
from pony import orm
from typing import Any
from inspect import getmembers, Signature, Parameter
from pony.orm import Required, Set, select, Optional, delete, desc, commit


sessionScope = orm.db_session
commit = orm.commit


@dataclass
class ColumnDetails:
    name: str
    primarykey: int
    type: Any
    nullable: bool
    collection: Any
    options: Any
    required: bool
    related_columns: Any
    default: Any

@dataclass
class TableDetails:
    name: str
    compoundkey: bool
    columns: ColumnDetails

def getHmiDetails(table) -> TableDetails:
    colum_names = [a.name for a in table._attrs_ if not a.is_collection]

    columndetails = {}
    for name in colum_names:
        a = getattr(table, name)
        default = a.default if a.default is not None else ''
        d = ColumnDetails(name=name,
                          primarykey=a.is_pk,
                          type=a.py_type,
                          # For now, relations are known by cols 0 and 1 (id and name)
                          related_columns= (a.py_type._attrs_[0]) if a.is_relation else None,
                          nullable=a.is_required,
                          collection=a.is_collection,
                          options=getattr(a.py_type, 'options', None),
                          required=a.is_required,
                          default=default)
        columndetails[name] = d
    return TableDetails(name=table.__name__, compoundkey=False, columns=columndetails)

the_db = orm.Database()


table_cache = {}


def DbTable(cls):
    """ Decorator that returns an ORM table definition from a class.
        As in the Message, annotations are used to define the table elements
    """
    if cls in table_cache:
        return table_cache[cls]
    # Currently, we use the PonyORM system.

    # Determine the various columns
    elements = {}
    for n, a in cls.__annotations__.items():
        try:
            default = getattr(cls, n)
            elements[n] = orm.Optional(a, default=default)

        except AttributeError:
            # The element is not assigned to.
            if isinstance(a, orm.core.Attribute):
                elements[n] = a
            else:
                elements[n] = orm.Optional(a)

    # Create the database class and return it.
    orm_cls = type(cls.__name__, (the_db.Entity,), elements)
    table_cache[cls] = orm_cls
    return orm_cls

def fields(cls):
    """ Mimics the API for dataclasses, but working on ponyorm database tables. """
    return cls._columns_

def url2path(url):
    """ For SQLite database, return the path to the database file """
    parts = urlparse(url)
    if parts.scheme == 'sqlite':
        path = parts.netloc or parts.path
        return path
    return None


class DbaseVersion(the_db.Entity):  # pylint:disable=W0232
    ''' Stores the version number of the database. '''
    version = orm.Required(int)


def openDb(url, version=1, update=None, create=True):
    ''' Create a new database from the URL
    '''
    if the_db.provider is not None:
        logging.error('Trying to initialise the database twice!')
        return
    parts = urlparse(url)
    if parts.scheme == 'sqlite':
        path = parts.netloc or parts.path
        if create and update and os.path.exists(path):
            update(path)
        the_db.bind(provider=parts.scheme, filename=path, create_db=create)
        the_db.generate_mapping(create_tables=create)
        with orm.db_session:
            if orm.count(d for d in DbaseVersion) == 0:
                v = DbaseVersion(version = version)

    else:
        raise RuntimeError('Database %s not supported'%parts.scheme)


