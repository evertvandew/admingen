
import os
from dataclasses import is_dataclass
from admingen.data.sqlite_db import SqliteDatabase, sessionmaker
from admingen.data import serialiseDataclass, deserialiseDataclass



db_path = '../data'
ID_OFFSET = 100000000

data_model = None
data_classes = {}

def set_datamodel(dm, dbname):
    global data_model, data_classes
    data_model = dm
    data_classes = {t.__name__: t for t in data_model.all_tables[dbname]}


def ensure_prerequisites(records):
    """ A decorator that ensures specific objects exist in the database before running a test,
        and that these are deleted after the test.
    """
    def wrapper(func):
        def doIt(self):
            # Mark the current state of the database, so it can be restored later.
            db_state = self.db_mark()
            self.db_clear()
            with self.db.Session() as session:
                for record in records:
                    # Add the offset to the relevant items in the records.
                    for key, t in record.get_fks().items():
                        value = getattr(record, key)
                        if isinstance(value, int) and value < ID_OFFSET:
                            setattr(record, key, value+ID_OFFSET)
                    if isinstance(record.id, int) and record.id < ID_OFFSET:
                        record.id += ID_OFFSET

                    session.add(record)

                session.commit()

            # The pre-requisites have been created. Run the test function.
            try:
                 func(self)
            finally:
                # Now delete the objects that were created.
                self.db_restore(db_state)
        return doIt
    return wrapper


def db_freeze(delta, f):
    """ write a delta to a single file. """
    for r in delta:
        f.write(f'{type(r).__name__},{serialiseDataclass(r)}\n')

def db_thaw(f):
    """ Read and deserialize records from a single file, and return them in a list """
    result = []
    for line in f:
        table, details = line.split(',', maxsplit=1)
        obj = deserialiseDataclass(data_classes[table], details)
        result.append(obj)
    return result


def SqlitedbPlugin(dbname):
    db = SqliteDatabase(data_model.database_urls[dbname],
                        data_model.all_tables[dbname],
                        data_model.database_registries[dbname])
    connection = db.engine.connect()
    class PluginCls:
        def db_clear(self):
            # Simply delete all objects in the database, and store the ones from the state.
            with self.db.Session() as session:
                for table in data_model.all_tables[dbname]:
                    session.execute(f"DELETE FROM {table.__name__}")
                session.commit()

        def db_mark(self):
            # Simply load all objects from the database into the state and return it
            state = []
            for table in data_model.all_tables[dbname]:
                state.extend(db.get_many(table))
            return state

        def db_restore(self, state):
            self.db_clear()
            with db.Session() as session:
                session.add_all(state)
                session.commit()

        def db_delta(self, state):
            """ Return all records in the current database that have changed with respect to the state """
            indexed_state = {(type(r).__name__, r.id): r for r in state}
            new_state = self.db_mark()
            new_indexed_state = {(type(r).__name__, r.id): r for r in new_state}
            delta = []
            for k, v in new_indexed_state.items():
                if k not in indexed_state or indexed_state[k] != v:
                    delta.append(v)
            return delta

    return PluginCls