"""
A dummy database that stores changes in-memory.
"""

import enum
from dataclasses import is_dataclass, asdict, fields
from typing import Union, Type, Callable, List
from admingen.data import serialiseDataclass, deserialiseDataclass
from .db_api import db_api, filter_context, Record


class UnknownRecord(RuntimeError): pass


class DummyDatabase(db_api):
    actions = enum.Enum('actions', 'add update delete')

    def __init__(self, tables):
        self.data = {}
        self.tables = tables
        self.hooks = {}
        self.active_hooks = set()
        self.create()

    def create(self):
        self.data = {t.__name__: {} for t in self.tables}

    def clear(self):
        """ Delete the whole structure and build anew, without any records """
        self.create()

    def add(self, table: Union[Type[Record], Record], record: Record = None) -> Record:
        """ Add a record to the database. The name of the type of the record must be the name of
            the table. The record is assumed to have the dictionary interface.
        """
        if record is None:
            record = table
            table = type(table)
        elif isinstance(record, dict):
            record = table(**record)

        data = self.data[table.__name__]

        self.call_hooks(type(record), self.actions.pre_add, record)
        if not getattr(record, 'id', None):
            # We need to know the highest current ID in the database
            record.id = max(data) + 1 if data else 1
        else:
            # Ensure the object does not already exist
            if record.id in data:
                raise RuntimeError('Record ID already exists', 400)
        data[record.id] = record
        self.call_hooks(type(record), self.actions.post_add, record)
        return record

    def set(self, record: Record) -> Record:
        data = self.data[type(record).__name__]
        self.call_hooks(type(record), self.actions.pre_update, record, data[record.id])
        data[record.id] = record
        self.call_hooks(type(record), self.actions.post_update, record)
        return record

    def update(self, table: Union[Type[Record], dict], record: dict = None,
               checker: Callable[[Record, dict], bool] = None) -> None:
        """ Update the values in an existing record.
            The record is identified by id, which can not be changed.
            Only the values in the record are updated (apart from id).

            'record' must be a dictionary. When storing a dataclass object,
            just use the set function.
        """
        if record is None:
            record = asdict(table)
            table = type(table)
        data = self.data[table.__name__]
        if not record['id'] in data:
            raise (UnknownRecord())

        data = data[record['id']].copy()
        if checker:
            if not checker(record, data):
                return


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

        self.call_hooks(table, self.actions.pre_update, data, data[record['id']])

        data[record['id']] = data

        self.call_hooks(table, self.actions.post_update, data)
        return data

    def delete(self, table: Type[Record], index: int) -> None:
        """ Delete an existing record. """
        data = self.data[table.__name__]
        if not index in data:
            raise (UnknownRecord())

        self.call_hooks(table, self.actions.pre_delete, data[index])
        del data[index]
        self.call_hooks(table, self.actions.post_delete, index)

    def get(self, table: Type[Record], index: int) -> Record:
        """ Retrieve a record identified by table name and index.
            The table is a dataclass with a name that is initialised with list of named
            arguments.
            With this method, you can also retrieve archived records.
        """
        if not index:
            return None
        data = self.data[table.__name__]
        if not index in data:
            raise (UnknownRecord())
        return data[index]

    def get_many(self, table: Type[Record], indices: List[int] = None) -> List[Record]:
        """ Retrieve a (large) set of records at once. There are returned as a list.
            If indices is not specified, empty or None, ALL records from the table are read.
        """
        data = self.data[table.__name__]
        if indices:
            return [data[i] for i in indices if i in data]
        return list(data.values())



