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
from sqlalchemy.orm import Session
from typing import List, Type, Union, Callable
from dataclasses import asdict

from .db_api import db_api, filter_context, Record


class SqliteDatabase(db_api):
    def __init__(self, path, tables, meta):
        self.tables = tables
        self.path = path
        self.meta = meta

        # Instantiate the database
        self.engine = create_engine(f"sqlite:///{self.path}", echo=True, future=True)
        meta.create_all(self.engine)


    def get(self, table: Type[Record], index: int) -> Record:
        with Session(self.engine) as session:
            return session.query(table).filter(table.id == index).one()

    def add(self, table: Union[Type[Record], Record], record: Record=None) -> Record:
        if record:
            # Ensure the record is of the right type
            record = table(record)
        else:
            record = table

        with Session(self.engine) as session:
            session.add(record)
            session.commit()
            return record

    def set(self, record: Record) -> Record:
        # Assume the record already exists, and we just need to update it.
        # The record was updated outside a session, so it won't commit automatically.
        update = record.asdict()
        T = type(record)
        with Session(self.engine) as session:
            session.query(type(record)).filter(T.id == update['id']).update(update, synchronize_session = False)
            return session.commit()

    def update(self, table: Union[Type[Record], dict], record: dict=None, checker: Callable[[Record, dict],bool]=None) -> Record:
        """ Update a record. Has an optional checker argument;
            the checker is for checking if the user is allowed to update a specific record.
        """
        raise NotImplementedError()

    def delete(self, table:Type[Record], index:int) -> None:
        raise NotImplementedError()

