""" SQLite database

Implementation of the simple DB API to work with the SQLite database engine.

I really like SQLite because it is fast and does not have global interfaces that
need protection. Just a file.
"""

import sqlalchemy as sq
from sqlalchemy.orm import registry
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.orm import sessionmaker
from typing import List, Type, Union, Callable
from dataclasses import asdict

from .db_api import db_api, filter_context, Record


class UnknownRecord(RuntimeError): pass


class SqliteDatabase(db_api):
    def __init__(self, path, tables, registry):
        db_api.__init__(self)
        self.tables = tables
        self.path = path + '.sqlite3'
        self.meta = registry.metadata

        # Instantiate the database
        self.engine = create_engine(f"sqlite:///{self.path}", echo=True, future=True)
        self.Session = sessionmaker(bind = self.engine, expire_on_commit=False)
        self.meta.create_all(self.engine)

        # Populate the reverse-lookup table
        rl = {}
        tables_lu = {t.__name__: t for t in tables}
        for m in self.meta.tables:
            rl[m.lower()] = tables_lu[m]
        registry.reverse_lookup = rl


    def get(self, table: Type[Record], index: int) -> Record:
        try:
            with self.Session() as session:
                result = session.query(table).filter(table.id == index).one()
                if result:
                    return result
        except sq.exc.NoResultFound:
            raise UnknownRecord()

    def get_many(self, table:Type[Record], indices:List[int]=None) -> List[Record]:
        """ Retrieve a (large) set of records at once. There are returned as a list.
            If indices is not specified, empty or None, ALL records from the table are read.
        """
        with self.Session() as session:
            result = session.query(table).all()
            return result

    def add(self, table: Union[Type[Record], Record], record: Record=None) -> Record:
        if record:
            # Ensure the record is of the right type
            record = table(record)
        else:
            record = table
        record.id = None

        with self.Session() as session:
            session.add(record)
            session.commit()
            return record

    def set(self, record: Record) -> Record:
        # Assume the record already exists, and we just need to update it.
        # The record was updated outside a session, so it won't commit automatically.
        update = record.asdict()
        T = type(record)
        with self.Session() as session:
            session.query(type(record)).filter(T.id == update['id']).update(update, synchronize_session = False)
            return session.commit()

    def update(self, table: Union[Type[Record], dict], record: dict=None, checker: Callable[[Record, dict],bool]=None) -> Record:
        """ Update a record. Has an optional checker argument;
            the checker is for checking if the user is allowed to update a specific record.
        """
        if record is None:
            record = table.asdict()
            table = type(table)
        if checker:
            # We need the current values to check if the update is valid
            data = self.get(table, record['id'])
            if not checker(record, data):
                return

        # Perform the update
        rid = record['id']
        del record['id']

        # Ensure all attributes have the correct type
        for k, v in record.items():
            record[k] = table.convert_field(k, v)

        with self.Session() as session:
            session.query(table).filter(table.id == rid).update(record)
            session.commit()
            result = table(**record)
            result.id = int(rid)
            return result

    def delete(self, table:Type[Record], index:int) -> None:
        with self.Session() as session:
            session.query(table).filter(table.id == index).delete()
            session.commit()

