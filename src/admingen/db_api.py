from collections import namedtuple
from pony import orm
from inspect import getmembers, Signature, Parameter
from pony.orm import Required, Set, select, Optional


sessionScope = orm.db_session
commit = orm.commit



# TODO: replace with dataclass once py3.7 is out
ColumnDetails = namedtuple('ColumnDetails', ['name', 'primarykey', 'type', 'relation', 'nullable',
                                             'collection', 'options', 'required'])


def getHmiDetails(table):
    details = {}
    details['name'] = table._table_
    details['compoundkey'] = False
    colum_names = [a.column for a in table._attrs_ if a.column]

    details['columns'] = {}
    for name in colum_names:
        a = getattr(table, name)
        d = ColumnDetails(name=name,
                          primarykey=a.is_pk,
                          type=a.py_type,
                          # For now, relations are known by cols 0 and 1 (id and name)
                          related_columns= (a.py_type._attrs_[0]) if a.is_relation else None,
                          nullable=a.is_required,
                          collection=a.is_colletion,
                          options=getattr(a.py_type, 'options', None),
                          required=a.is_required)
        details['columns'][name] = d
    return details

the_db = orm.Database()


def DbTable(cls):
    """ Decorator that returns an ORM table definition from a class.
        As in the Message, annotations are used to define the table elements
    """
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
    return type(cls.__name__, (the_db.Entity,), elements)
