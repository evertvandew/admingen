from typing import Dict, Set, List
from builtins import *  # So they can be accessed from the CuriousEnv
import re
import types
from collections import namedtuple
from decimal import Decimal
from datetime import datetime, date, time, timedelta
import logging

from pony import orm
from pony.orm import Set   # Can be used by the configuration

import cherrypy

from .parsers import fsm_model as model
from .htmltools import generateCrud

# TODO: when py3.7 replace with data classes
Message = namedtuple('Message', ['method', 'path', 'details'])
Transition = namedtuple('Transition', ['fsm', 'start', 'end'])


# TODO: Missing in the syntax is the possibility to have COMMENTS.
# TODO: support for default values in columns
# TODO: support for embedded files (blobs) and files on disk.

# We should accept escaped newlines in arguments, but this does not work:
# arguments = /(([^\n\\]|(\\[\n\\\'\"abfnrtvx\d]))*)/ ;


transre = re.compile(
    r'(?P<start>(\w+)|(\[\*\]))\s*-?->\s*(?P<end>(\w+)|(\[\*\]))(\s*:\s*(?P<msg>.*))?')
datare = re.compile(
    r'(?P<column>\w+)\s*:\s*(?P<type>[0-9a-zA-Z()]+)(\s*,\s*(?P<options>([^,]+\s*,\s*)+))?')


class Error(RuntimeError): pass

class email(str): pass


class blob(bytes): pass


class telefoonnr(str): pass


class money(Decimal): pass


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



explicit_match = re.compile(r'((Set)|(Optional)|(Required))\(.*\)')


def parseColumnDetails(s:str, track: TrackingEnv):
    """ Parse the details. Two cases are supported:
            1: The details are an explicit call to orm.Set, orm.Optional, orm.Required etc.
            2: The details for a set of arguments to orm.Optional.
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
    db = orm.Database()
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


def determineMsgHandlers(fsms):
    """ Create a lookup table to handle the msgs for the different state machines """
    lookup = {}
    for name, transitions in [(fsm['name'], fsm['transitions']) for fsm in fsms]:
        for tr in transitions:
            msg = tr['details']
            if msg is None and tr['from'] == '[*]':
                msg = 'add'
            elif msg is None and tr['to'] == '[*]':
                msg = 'delete'
            t = Transition(name, tr['from'], tr['to'])
            lookup.setdefault(msg, {})[name] = t
    return lookup


def readconfig(stream):
    ast = model.parse(stream.read(), start='projects', whitespace=r'[ \t\r]')
    transitions = determineMsgHandlers(ast['fsms'])
    fsm_names = [fsm['name'] for fsm in ast['fsms']]
    db, dbmodel = createDbModel(ast['tables'], fsm_names)
    return transitions, db, dbmodel


def engine(transitions: Dict[str, Dict[str, Transition]],
           model: Dict[str, orm.core.Entity]):
    """ Transitions is a msg : [transition] dictionary
        model is a table : db.Entity dictionary
    """

    def handle(msg):
        path = msg.path.strip('/').split('/')
        # The method and first part of the path show which transition is requested.
        trans = transitions[msg.method]
        trans = trans.get(path[0], None)

        if not trans:
            raise Error(400)

        # Construct the query to execute the transition
        # We are using the PonyORM
        entity_cls = model[trans.fsm]
        with orm.db_session():
            # Check if we need to add a new element
            if msg.method == 'add':
                _ = entity_cls(state=trans.end, **msg.details)
            else:
                # We need to update existing records
                # Currently, pony does not support update queries...
                for i in [i for i in entity_cls if trans.start == '[*]' or i.state == trans.start]:
                    i.state = trans.end

    return handle
