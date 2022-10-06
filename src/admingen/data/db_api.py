
import enum
import operator
from typing import List, Type, Union, Callable
from dataclasses import asdict

# Define the operators that can be used in filter and join conditions
filter_context = {
    'isIn': operator.contains,
    'isTrue': lambda x: x.lower()=='true',
    'isFalse': lambda x: x.lower()!='true',
    'and_': operator.and_,
    'eq': operator.eq,
    'neq': operator.ne,
    'lt': operator.lt,
    'gt': operator.gt,
    'le': operator.le,
    'ge': operator.ge
}

# A base class to be used in typeing.
class Record: pass



def getJsonJoined(a_cls, b_cls):
    """ Return an function that returns something that is jsonified """
    def jsonify(self):
        result = asdict(self)
        result[b_cls.__name__] = asdict(getattr(self, b_cls.__name__))
        return result
    return jsonify


class db_api:
    """ A simple API for a data base.
        Also defines some algorithms that make use of the low-level functions,
        but can be overwritten by classes that use e.g. SQL to implement these algorithms.
    """
    actions = enum.Enum('actions', 'add update delete')
    has_acm = False
    def __init__(self):
        self.hooks = {}
        self.active_hooks = set()
    def get(self, table: Type[Record], index: int) -> Record:
        raise NotImplementedError()
    def add(self, table: Union[Type[Record], Record], record: Record=None) -> Record:
        raise NotImplementedError()
    def set(self, record: Record) -> Record:
        raise NotImplementedError()
    def update(self, table: Union[Type[Record], dict], record: dict=None, checker: Callable[[Record, dict],bool]=None) -> Record:
        """ Update a record. Has an optional checker argument;
            the checker is for checking if the user is allowed to update a specific record.
        """
        raise NotImplementedError()
    def delete(self, table:Type[Record], index:int) -> None:
        raise NotImplementedError()


    def data_hook(self, table):
        """ Decorator that defines a hook for updates on data of a specific type.
        """
        def add_hook(hook):
            hooks = self.hooks.setdefault(table.__name__, [])
            hooks.append(hook)
            return hook
        return add_hook

    def call_hooks(self, table, action, record):
        # Call the hooks, but make sure there is no recursion.
        for hook in self.hooks.get(table.__name__, []):
            if hook not in self.active_hooks:
                self.active_hooks.add(hook)
                try:
                    hook(action, record)
                finally:
                    self.active_hooks.remove(hook)

    def get_many(self, table:Type[Record], indices:List[int]=None) -> List[Record]:
        """ Retrieve a (large) set of records at once. There are returned as a list.
            If indices is not specified, empty or None, ALL records from the table are read.
        """
        raise NotImplementedError()

    def query(self, table:Type[Record], filter=None, join=None, resolve_fk=None,
              sort=None, limit=None) -> List[Record]:
        """ A simple query function that uses in-memory filtering.
            A join can be defined by supplying a tuple with a Table name and
            a lambda function expecting two arguments that returns True if they match.
            The first argument is the original table, the second the table being joined.
            A filter can be supplied as a lambda function that receives
            a record as argument.
        """
        # We need to make an object of the whole contents of a directory
        records = self.get_many(table)

        if resolve_fk:
            for member, ftable in table.get_fks().items():
                ids = [getattr(r, member) for r in records]
                ids_set = list(set(ids))
                foreigns = {(r and r.id): r for r in self.get_many(ftable, ids_set)}
                for r in records:
                    setattr(r, member, foreigns.get(getattr(r, member), None))

        if join:
            b_records = self.query(join[0])
            for rec in records:
                tname = join[0]
                if not isinstance(tname, str):
                    tname = tname.__name__
                setattr(rec, tname, None)
                for b in b_records:
                    if join[1](rec, b):
                        setattr(rec, tname, b)
                        rec.__json__ = getJsonJoined(table, join[0]).__get__(rec, rec.__class__)
                        break

        if filter:
            records = [rec for rec in records if filter(rec)]
        return records




def update_unique(db, table, new_data, pk=['id']):
    """ Update a table in the database.
        Only add unique records, according to the primary key.
        The primary key can be composite (multiple columns).
    """
    # Get all existing records
    original = db.query(table)

    # Create a set of existing primary keys
    known_keys = set((getattr(r, k) for k in pk) for r in original)
    for r in new_data:
        key = (getattr(r, k) for k in pk)
        if key not in known_keys:
            if hasattr(r, 'id') and r.id:
                r.id = None
            db.add(r)
            known_keys.add(key)
