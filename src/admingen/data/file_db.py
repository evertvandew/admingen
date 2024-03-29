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
import shutil
import functools
from copy import copy
from urllib.parse import unquote
from dataclasses import is_dataclass, asdict, fields
from typing import Union, Type, Callable, List
from admingen.data import serialiseDataclass, deserialiseDataclass
from .db_api import db_api, filter_context, Record, DbActions


class UnknownRecord(RuntimeError): pass


the_db = None

def multi_sort(descriptor, data):
    """ A function to sort a list of data (dictionaries).
        The sort descriptor is a comma-separated string of keys into the dicts.
        Optionally, the key is followed by the word ":desc", for example
            "a,b:desc,c"
    """
    sorts = descriptor.split(',')

    def sort_predicate_dict(it1: dict, it2: dict):
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

    def sort_predicate_cls(it1, it2):
        for key in sorts:
            sort_desc = False
            sort_desc = key.endswith(':desc')
            if sort_desc:
                key = key.split(':')[0]
            # Retrieve the values to be sorted on now.
            v1, v2 = [getattr(i, key) for i in [it1, it2]]
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

    if data and isinstance(data[0], dict):
        return sorted(data, key=functools.cmp_to_key(sort_predicate_dict))
    return sorted(data, key=functools.cmp_to_key(sort_predicate_cls))


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


class FileDatabase(db_api):
    def __init__(self, path, tables):
        db_api.__init__(self)
        self.archive_dir = 'archived'
        self.path = path
        self.tables = tables
        self.create()

    def create(self):
        path = self.path
        if not os.path.exists(path):
            os.mkdir(path)
        
        for table in self.tables:
            name = table.__name__
            tp = os.path.join(path, name)
            if not os.path.exists(tp):
                os.mkdir(tp)
            ad = os.path.join(tp, self.archive_dir)
            if not os.path.exists(ad):
                os.mkdir(ad)
        self.transactionEnd()
                
    def clear(self):
        """ Delete the whole structure and build anew, without any records """
        shutil.rmtree(self.path)
        self.create()
        
    
    def add(self, table: Union[Type[Record], Record], record: Record=None) -> Record:
        """ Add a record to the database. The name of the type of the record must be the name of
            the table. The record is assumed to have the dictionary interface.
        """
        if record is None:
            record = table
            table = type(table)
        elif isinstance(record, dict):
            record = table(**record)

        self.call_hooks(type(record), self.actions.pre_add, record)

        fullpath = os.path.join(self.path, table.__name__)
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
        self.transactionLog(DbActions.delete, {'table': table, 'id': record.id})
        self.call_hooks(type(record), self.actions.post_add, record)
        return record
    
    def set(self, record: Record) -> Record:

        fullpath = f"{self.path}/{type(record).__name__}/{record.id}"
        # Retrieve and store the old value for logging
        current = self.get(type(record), record.id)
        self.call_hooks(type(record), self.actions.pre_update, record, current)
        self.transactionLog(DbActions.update, current)
        data_str = serialiseDataclass(record)
        with open(fullpath, "w") as dest_file:
            dest_file.write(data_str)
        self.call_hooks(type(record), self.actions.post_update, record)
        return record

    def update(self, table: Union[Type[Record], dict], record: dict=None, checker: Callable[[Record, dict],bool]=None) -> None:
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

        current = copy(data)
        self.transactionLog(DbActions.update, current)

        # Update with the new data
        for k, v in record.items():
            if k not in table.__annotations__.keys():
                # This is not an actual attribute of this table.
                # This is not an error: clients are free to enrich their objects.
                continue
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

        self.call_hooks(table, self.actions.pre_update, data, current)

        # Now serialize
        data_str = serialiseDataclass(data)
        with open(fullpath, "w") as dest_file:
            dest_file.write(data_str)
        self.call_hooks(table, self.actions.post_update, data)
        return data
            
    def delete(self, table:Type[Record], index:int) -> None:
        """ Delete an existing record. """
        fullpath = f"{self.path}/{table.__name__}/{index}"
        if not os.path.exists(fullpath):
            raise(UnknownRecord())
        data = deserialiseDataclass(table, open(fullpath).read())
        self.call_hooks(table, self.actions.pre_delete, data)

        # Don't actually delete the record, move it to the "archived" directory
        ad = f"{self.path}/{table.__name__}/{self.archive_dir}"
        if not os.path.exists(ad):
            os.mkdir(ad)
        newpath = f"{ad}/index"
        os.rename(fullpath, newpath)
        self.call_hooks(table, self.actions.post_delete, index)
    def undoDelete(self, data):
        fullpath = f"{self.path}/{table.__name__}/{index}"
        ad = f"{self.path}/{table.__name__}/{self.archive_dir}"
        newpath = f"{ad}/index"
        os.rename(newpath, fullpath)
    def ll_get(self, table, index):
        """ Low-level getter that is used by both `get` and `get_many`.
            The low-level getter is not overridden by e.g. the ACM wrapper, so this can
            also be used for raw access to the database. E.g. to check login credentials.
        """
        if not index:
            return None
        fullpath = f"{self.path}/{table.__name__}/{index}"
        #print('Retrieving', fullpath)
        if not os.path.exists(fullpath):
            # See if that object was archived.
            fullpath = f"{self.path}/{table.__name__}/{self.archive_dir}/{index}"
            if not os.path.exists(fullpath):
                raise(UnknownRecord(fullpath))
        data = open(fullpath).read()
        return deserialiseDataclass(table, data)


    def get(self, table: Type[Record], index: int) -> Record:
        """ Retrieve a record identified by table name and index.
            The table is a dataclass with a name that is initialised with list of named
            arguments.
            With this method, you can also retrieve archived records.
        """
        return self.ll_get(table, index)

    def get_many(self, table:Type[Record], indices:List[int]=None) -> List[Record]:
        """ Retrieve a (large) set of records at once. There are returned as a list.
            If indices is not specified, empty or None, ALL records from the table are read.
        """
        indices = indices or [int(f) for f in os.listdir(f"{self.path}/{table.__name__}") if f.isnumeric()]
        records = [self.ll_get(table, i) for i in indices]
        records = [r for r in records if r]
        return records
