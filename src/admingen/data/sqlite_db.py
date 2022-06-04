""" SQLite database

Implementation of the simple DB API to work with the SQLite database engine.

I really like SQLite because it is fast and does not have global interfaces that
need protection. Just a file.
"""

from sqlalchemy.orm import registry
from sqlalchemy import create_engine

from .db_api import db_api, filter_context, Record


class SqliteDatabase(db_api):
    def __init__(self, path, tables):
        self.tables = tables
        self.path = path

        # Map the tables to SQLAlchemy
        mapper_registry = registry()
        for table in self.tables:
            mapper_registry.map_imperatively(table)

        # Instantiate the database
        engine = create_engine(f"sqlite://{self.path}", echo=False, future=True)
