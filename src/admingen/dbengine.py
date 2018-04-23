

from datetime import datetime, date
from builtins import *  # So they can be accessed from the TrackingEnv
import re
from decimal import Decimal
import logging

from pony import orm

from .db_api import the_db, Set, Required, Optional


# TODO: support for default values in columns
# TODO: support for embedded files (blobs) and files on disk.


class email(str): pass


class blob(bytes): pass


class telefoonnr(str): pass


class money(Decimal): pass

class text(str): pass


class TrackingEnv(dict):
    """ This environment tries to get an object from the globals,
        but if this is not possible it returns the item key and makes note of it
    """

    def __init__(self):
        dict.__init__(self)
        self.missing = set()

    def __getitem__(self, item):
        try:
            return globals()[item]
        except KeyError:
            self.missing.add(item)
            return item



explicit_match = re.compile(r'((Set)|(Optional)|(Required)|(StateVariable))\(.*\)')


def StateVariable(fsm_name):
    """ Special handler for state variables in variables.
        The database model does nothing special with these variable, they are used by the GUI
        and the FSM specification.
    """
    return orm.Optional(str)


def parseColumnDetails(s:str, track: TrackingEnv):
    """ Parse the details. Two cases are supported:
            1: The details are an explicit call to orm.Set, orm.Optional, orm.Required etc.
            2: The details for a set of arguments to orm.Optional.
        Returns a PonyORM column specification (Optional, Required, Set etc)
    """
    if explicit_match.match(s):
        # This is an explicit call, execute it.
        return eval(s, track)
    # There follows a set of arguments for Optional.
    # Split into seperate arguments, and feed them to Optional.
    parts = s.split(',')
    args = []
    kwargs = {}
    for p in parts:
        if '=' in p:
            k, v  = p.split('=')
            kwargs[k.strip()] = eval(v)
        else:
            args.append(eval(p, track))
    return orm.Optional(*args, **kwargs)


def createDbModel(tables, fsm_names):
    """ Instantiate the database tables """
    trackingenv = TrackingEnv()   # Track references to tables
    db = the_db
    db_model = {}
    for table in tables:
        name = table['name']
        columns = {}
        for column in table['columns']:
            coltype = parseColumnDetails(column['details'], trackingenv)
            if coltype in [bytes, blob]:
                continue
            # If the coltype is not already a Pony Attribute, wrap it in an 'Optional'
            columns[column['name']] = coltype if isinstance(coltype, orm.core.Attribute) \
                else orm.Optional(coltype)
        # Tables linked to an FSM have an extra 'state' column
        # TODO: Re-enable the states
        if False and name in fsm_names:
            assert 'state' not in columns, 'FSM table %s can not have a column "state"'%name
            columns['state'] = orm.Required(str)
        db_model[name] = type(name, (db.Entity,), columns)

    errors = False
    # Check all references to tables are resolved
    for m in trackingenv.missing:
        if m not in db_model:
            logging.error('There was a reference to undefined data type %s' % m)
            errors = True
    # Check all fsm's have a database table
    for fsm in fsm_names:
        if fsm not in db_model:
            logging.error('No model found for fsm %s' % fsm)
            errors = True
            continue

    if errors:
        raise RuntimeError('Errors while parsing the configuration')

    return db, db_model
