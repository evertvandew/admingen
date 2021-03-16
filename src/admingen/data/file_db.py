""" File Database

The file database is simply a database stored directly on the file system, mainly for
testing purposes.

The database consists of a set of directories (the database tables) that contains
simple JSON files (the records). The files are named by the ID of the record --
all records have a simple integer primary key that is auto-numbered by the database.

This module defines a simple class that is the API to this database.
"""

import os, os.path
import enum
import json
import operator
import shutil
import functools
from urllib.parse import unquote
from dataclasses import is_dataclass, asdict

from admingen.data import serialiseDataclass, deserialiseDataclass, serialiseDataclasses


class UnknownRecord(RuntimeError): pass


the_db = None


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


def multi_sort(descriptor, data):
    """ A function to sort a list of data (dictionaries).
        The sort descriptor is a comma-separated string of keys into the dicts.
        Optionally, the key is followed by the word ":desc", for example
            "a,b:desc,c"
    """
    sorts = descriptor.split(',')

    def sort_predicate(it1, it2):
        for key in sorts:
            sort_desc = False
            sort_desc = key.endswith(':desc')
            if sort_desc:
                key = key.split(':')[0]
            # Retrieve the values to be sorted on now.
            v1, v2 = [i[key] for i in [it1, it2]]
            # Do the actual comparison
            if sort_desc:
                result = (v2 > v1) - (v2 < v1)
            else:
                result = (v1 > v2) - (v1 < v2)
            # If there is a difference based on the current key, return the value
            if result != 0:
                return result
        # There was no difference in any of the keys, return 0.
        return 0

    return sorted(data, key=functools.cmp_to_key(sort_predicate))


def do_leftjoin(tabl1, tabl2, data1, data2, condition):
    condition = unquote(condition)
    # Make the association.
    results = []
    for d1 in data1:
        if is_dataclass(d1):
            d1 = asdict(d1)

        def eval_cond(d2):
            """ Function returns true if d2 is to be joined to d1 """
            local_context = {tabl1: d1, tabl2: d2}
            local_context.update(d2)
            local_context.update(d1)
            return bool(eval(condition, filter_context, local_context))

        d2s = list(filter(eval_cond, data2))
        assert len(d2s) <= 1, "Join condition %s didn't result in a unique match" % condition
        result = {}
        if d2s:
            result.update(d2s[0])
            result[tabl2] = d2s[0]
        result[tabl1] = d1
        result.update(d1)
        results.append(result)
    return results


class FileDatabase:
    actions = enum.Enum('actions', 'add update delete')
    def __init__(self, path, tables):
        self.archive_dir = 'archived'
        self.path = path
        self.tables = tables
        self.create()
        self.hooks = {}
        self.active_hooks = set()

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

    def create(self):
        path = self.path
        if not os.path.exists(path):
            os.mkdir(path)
        
        for table in self.tables:
            tp = os.path.join(path, table.__name__)
            if not os.path.exists(tp):
                os.mkdir(tp)
            ad = os.path.join(tp, self.archive_dir)
            if not os.path.exists(ad):
                os.mkdir(ad)
                
    def clear(self):
        """ Delete the whole structure and build anew, without any records """
        shutil.rmtree(self.path)
        self.create()
        
    
    def add(self, record):
        """ Add a record to the database. The name of the type of the record must be the name of
            the table. The record is assumed to have the dictionary interface.
        """
        fullpath = os.path.join(self.path, type(record).__name__)
        print('FULLPATH:', fullpath)
        if not getattr(record, 'id', None):
            # We need to know the highest current ID in the database
            ids = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
            record.id = max(ids) + 1 if ids else 1
            archived = [int(f) for f in os.listdir(f"{fullpath}/{self.archive_dir}") if f.isnumeric()]
            if archived and (i:=max(archived)) >= record.id:
                    record.id = i+1
        else:
            # Ensure the object does not already exist
            if str(record.id) in os.listdir(fullpath):
                raise RuntimeError('Record ID already exists', 400)
        fullpath = f'{fullpath}/{record.id}'
        data_str = serialiseDataclass(record)
        with open(fullpath, "w") as dest_file:
            dest_file.write(data_str)
        self.call_hooks(type(record), self.actions.add, record)
        return record
    
    def set(self, record):
        fullpath = f"{self.path}/{type(record).__name__}/{record.id}"
        data_str = serialiseDataclass(record)
        with open(fullpath, "w") as dest_file:
            dest_file.write(data_str)
        self.call_hooks(type(record), self.actions.update, record)
        return record

    def update(self, table, record=None, checker=None):
        """ Update the values in an existing record.
            The record is identified by id, which can not be changed.
            Only the values in the record are updated (apart from id).
            
            'record' must be a dictionary. When storing a dataclass object,
            just use the set function.
        """
        if record is None:
            record = asdict(table)
            table = type(table)
        fullpath = f"{self.path}/{table.__name__}/{record['id']}"
        if not os.path.exists(fullpath):
            raise(UnknownRecord())

        # Make an initial data object for merging old and new data
        data = deserialiseDataclass(table, open(fullpath).read())

        if checker:
            if not checker(record, data):
                return

        # Update with the new data
        for k, v in record.items():
            if k == 'id':
                # The ID attribute can not be changed.
                continue
            if v is None or (isinstance(v, str) and v in ['None', 'null', '']):
                value = None
            else:
                if not v or type(v) != data.__annotations__[k]:
                    value = data.__annotations__[k](v)
                else:
                    value = v
            setattr(data, k, value)
        
        # Now serialize
        data_str = serialiseDataclass(data)
        with open(fullpath, "w") as dest_file:
            dest_file.write(data_str)
        self.call_hooks(table, self.actions.update, data)
        return data
            
    def delete(self, table, index):
        """ Delete an existing record. """
        fullpath = f"{self.path}/{table.__name__}/{index}"
        if not os.path.exists(fullpath):
            raise(UnknownRecord())

        # Don't actually delete the record, move it to the "archived" directory
        ad = f"{self.path}/{table.__name__}/{self.archive_dir}"
        if not os.path.exists(ad):
            os.mkdir(ad)
        newpath = f"{ad}/index"
        os.rename(fullpath, newpath)
        self.call_hooks(table, self.actions.delete, index)


    def get(self, table, index):
        """ Retrieve a record identified by table name and index.
            The table is a dataclass with a name that is initialised with list of named
            arguments.
            With this method, you can also retrieve archived records.
        """
        if not index:
            return None
        fullpath = f"{self.path}/{table.__name__}/{index}"
        if not os.path.exists(fullpath):
            # See if that object was archived.
            fullpath = f"{self.path}/{table.__name__}/{self.archive_dir}/{index}"
            if not os.path.exists(fullpath):
                raise(UnknownRecord())
        data = open(fullpath).read()
        return deserialiseDataclass(table, data)

    def get_many(self, table, indices=None):
        """ Retrieve a (large) set of records at once. There are returned as a list.
            If indices is not specified, empty or None, ALL records from the table are read.
        """
        indices = indices or [int(f) for f in os.listdir(f"{self.path}/{table.__name__}") if f.isnumeric()]
        records = [self.get(table, i) for i in indices]
        records = [r for r in records if r]
        return records

    
    def query(self, table, filter=None, join=None, resolve_fk=None, sort=None, limit=None):
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
                foreigns = {(r and r.id): r for i, r in zip(ids_set, self.get_many(ftable, ids_set))}
                for r, i in zip(records, ids):
                    setattr(r, member, foreigns.get(i, None))

        if join:
            b_records = self.query(join[0])
            for rec in records:
                setattr(rec, join[0].__name__, None)
                for b in b_records:
                    if join[1](rec, b):
                        setattr(rec, join[0].__name__, b)
                        break

        if filter:
            records = [rec for rec in records if filter(rec)]
        return records
