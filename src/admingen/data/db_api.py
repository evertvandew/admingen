

import operator


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



class db_api:
    """ A simple API for a data base """

    def get(self, table, index):
        raise NotImplementedError()
    def add(self, table, record=None):
        raise NotImplementedError()
    def set(self, record):
        raise NotImplementedError()
    def update(self, record):
        raise NotImplementedError()
    def delete(self, table, index):
        raise NotImplementedError()


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
                tname = join[0]
                if not isinstance(tname, str):
                    tname = tname.__name__
                setattr(rec, tname, None)
                for b in b_records:
                    if join[1](rec, b):
                        setattr(rec, tname, b)
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
