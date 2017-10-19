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

Message = namedtuple('Message', ['method', 'path', 'details'])
Transition = namedtuple('Transition', ['fsm', 'start', 'end'])


syntax = r'''
config = [modules] '\n'%{[ fsm | table | rules | actions ]} ;

modules = "import" module NEWLINE ;
module  = "."%{ name } ; 
name = /\w+/ ;

fsm = "fsm" name "\n" transitions blockend ;
transitions = {[transition] NEWLINE} ;
transition = !(".\n") ','%{state} /\s*-?->\s*/ state [":" restofline] ;
state = name | "[*]" ;
blockend = "." ;

table = "table" name NEWLINE columns blockend ;
columns = {[column] NEWLINE} ;
column = !(".\n") name ":" restofline ;

rules = "rules" name NEWLINE rule_lines blockend ;
rule_lines = {[rule] NEWLINE} ;
rule = !(".\n") /\s*,\s*/%{ name } ":" restofline ;


actions = "actions" "."%{name} NEWLINE action_lines blockend;
action_lines = {[rule] NEWLINE} ;
action = !(".\n") "\s*,\s*"%{ name } ":" restofline ;

NEWLINE = (SPACES | (['\\r'] /[\n\r\f]/) [SPACES]) ;
SPACES = /[ \t]+/ ;
restofline = /[^\n]*/ ;
'''

# TODO: Missing in the syntax is the possibility to have COMMENTS.

# We should accept escaped newlines in arguments, but this does not work:
# arguments = /(([^\n\\]|(\\[\n\\\'\"abfnrtvx\d]))*)/ ;


transre = re.compile(
    r'(?P<start>(\w+)|(\[\*\]))\s*-?->\s*(?P<end>(\w+)|(\[\*\]))(\s*:\s*(?P<msg>.*))?')
datare = re.compile(
    r'(?P<column>\w+)\s*:\s*(?P<type>[0-9a-zA-Z()]+)(\s*,\s*(?P<options>([^,]+\s*,\s*)+))?')


class email(str): pass


class blob(bytes): pass


class telefoonnr(str): pass


class money(Decimal): pass


class CuriousEnv(dict):
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


def readconfig(stream):
    curiousenv = CuriousEnv()

    def readTransistions(transitions, name):
        for line in stream:
            if line.startswith('@endtrans'):
                return
            m = transre.match(line)
            if m:
                d = m.groupdict()
                msg = d.get('msg', None)
                if msg is None and d['start'] == '[*]':
                    msg = 'add %s' % name
                t = Transition(name, d['start'], d['end'])
                transitions.setdefault(msg, []).append(t)

    def readTable(model, name):
        columns = {}
        for line in stream:
            if line.startswith('@enddata'):
                model[name] = columns
                return
            m = datare.match(line)
            if m:
                d = m.groupdict()
                typestr = d['type']
                if typestr.startswith('Set('):
                    _i_ = 0

                coltype = eval(d['type'], curiousenv)

                if isinstance(coltype, orm.core.Attribute):
                    columns[d['column']] = coltype
                else:
                    # If the coltype is not already a Pony Attribute, wrap it in an 'Optional'
                    columns[d['column']] = orm.Optional(coltype)

    transitions = {}
    model = {}

    for line in stream:
        if line.startswith('@starttrans'):
            parts = line.split()
            readTransistions(transitions, parts[1].strip())

        if line.startswith('@startdata'):
            parts = line.split()
            readTable(model, parts[1])

    errors = False
    # Give all tables associated with statemachines an extra 'state' column
    fsms = set(t.fsm for ts in transitions.values() for t in ts)
    for fsm in fsms:
        if fsm not in model:
            logging.error('No model found for fsm %s' % fsm)
            errors = True
            continue
        model[fsm]['state'] = orm.Required(str)

    # Check that all foreign references exist
    for m in curiousenv.missing:
        if m not in model:
            logging.error('There was a reference to undefined data type %s' % m)
            errors = True

    if errors:
        raise RuntimeError('Errors while parsing the configuration')

    # Create a database and define the tables
    # This database is NOT mapped to any real database yet!
    db = orm.Database()
    model = {table: type(table, (db.Entity,), columns) for table, columns in model.items()}

    return transitions, db, model


def engine(transitions: Dict[str, List[Transition]],
           model: Dict[str, orm.core.Entity]):
    """ Transitions is a msg : [transition] dictionary
        model is a table : db.Entity dictionary
    """

    def handle(msg):
        path = msg.path.strip('/')
        name = '%s %s' % (msg.method, path) if path else msg.method
        for trans in transitions[name]:
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
