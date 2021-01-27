""" File Database

The file database is simply a database stored directly on the file system, mainly for
testing purposes.

The database consists of a set of directories (the database tables) that contains
simple JSON files (the records). The files are named by the ID of the record --
all records have a simple integer primary key that is auto-numbered by the database.

This module defines a simple class that is the API to this database.
"""

import os, os.path
import json
import shutil
from admingen.data import serialiseDataclass, deserialiseDataclass, serialiseDataclasses


class UnknownRecord(RuntimeError): pass


the_db = None


class FileDatabase:
    def __init__(self, path, tables):
        self.path = path
        self.tables = tables
        self.create()
    
    def create(self):
        path = self.path
        if not os.path.exists(path):
            os.mkdir(path)
        
        for table in self.tables:
            tp = os.path.join(path, table.__name__)
            if not os.path.exists(tp):
                os.mkdir(tp)
                
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
        fullpath = f'{fullpath}/{record.id}'
        data_str = serialiseDataclass(record)
        with open(fullpath, "w") as dest_file:
            dest_file.write(data_str)
        return record
    
    def set(self, record):
        fullpath = f"{self.path}/{type(record).__name__}/{record.id}"
        data_str = serialiseDataclass(record)
        with open(fullpath, "w") as dest_file:
            dest_file.write(data_str)
        return record

    def update(self, table, record):
        """ Update the values in an existing record.
            The record is identified by id, which can not be changed.
            Only the values in the record are updated (apart from id).
            
            'record' must be a dictionary. When storing a dataclass object,
            just use the set function.
        """
        fullpath = f"{self.path}/{table.__name__}/{record['id']}"
        if not os.path.exists(fullpath):
            raise(UnknownRecord())

        # Make an initial data object for merging old and new data
        data = deserialiseDataclass(table, open(fullpath).read())

        # Update with the new data
        for k, v in record.items():
            if k == 'id':
                # The ID attribute can not be changed.
                continue
            if v in [None, 'None', 'null', '']:
                value = None
            else:
                value = data.__annotations__[k](v)
            setattr(data, k, value)
        
        # Now serialize
        data_str = serialiseDataclass(data)
        with open(fullpath, "w") as dest_file:
            dest_file.write(data_str)
        return data
            
    def delete(self, table, index):
        """ Delete an existing record. """
        fullpath = f"{self.path}/{table.__name__}/{index}"
        if not os.path.exists(fullpath):
            raise(UnknownRecord())
        os.remove(fullpath)

    def get(self, table, index):
        """ Retrieve a record identified by table name and index.
            The table is a dataclass with a name that is initialised with list of named
            arguments.
        """
        fullpath = f"{self.path}/{table.__name__}/{index}"
        if not os.path.exists(fullpath):
            raise(UnknownRecord())
        data = open(fullpath).read()
        return deserialiseDataclass(table, data)
    
    def query(self, table, filter=None, sort=None, limit=None):
        """ A simple query function that uses in-memory filtering. """
        fullpath = f"{self.path}/{table.__name__}"
        
        # We need to make an object of the whole contents of a directory
        entries = [int(f) for f in os.listdir(fullpath) if f.isnumeric()]
        data = [open(os.path.join(fullpath, str(e))).read() for e in entries]
        
        return [deserialiseDataclass(table, s) for s in data]
