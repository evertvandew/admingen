#!/usr/bin/env python3
""" A simple stand-alone program to handle a state machine.

Receives input from stdin, and writes actions to stdout.

After UNIX tradions, all input & output is in an ASCII protocol.

The protocol is as follows:

 * `add <name>`: Voeg een nieuwe instantie van de state machine toe/
 * `when in <state> and <condition> goto <newstate>`: Voeg een nieuwe transitie toe.
 * `check`: Check whether the rules of the FSM are consistent. Does simple checks, e.g.
    if the FSM has unreachable states.
 * `event <name> for <name>`: Inform the FSM that an event occurred in the context of a
    specific FSM instance.
 * `set <iname>.<variable> <value>`: Set a value in the context of an FSM instance.
"""

import sys
import json
import bcrypt
import os
import copy
import argparse


def length(it):
    return len(list(it))

def avg(it):
    l = list(it)
    return sum(l)/len(l)


# Create a default document directory.
documents = {}
# The login details for users are kept in a separate data structure
salt = os.urandom(64)

def password2str(value):
    salt = bcrypt.gensalt()
    hash = bcrypt.hashpw(value, salt)
    return hash

def checkpasswd(clear, hashed):
    return bcrypt.checkpw(clear, hashed)

users = {'admin': {'password': password2str('testing'), 'groups': [0]}}
groups = ['admin']
transitions = {}  # event : doctypes : state1 : condition : state2

class DocumentAccessor:
    def __init__(self, docs):
        self.docs = docs
    def __getitem__(self, key):
        if key in self.docs:
            return self.docs[key]
        print('Item %s does not exist'%key, file=sys.stderr)
        return None
    def __iter__(self):
        return iter(self.docs.values())


env = {'docs': DocumentAccessor(documents), 'max': max, 'min': min, 'sum': sum, 'avg': avg}



def execute_event(event):
    """ Evaluate an event """
    for doctype, states in transitions.get(event, {}).items():
        for state1, conditions in states.items():
            for condition, state2 in conditions.items():
                relevant_docs = [d for d in documents if d['type']==doctype and d['state']==state1]
                for d in relevant_docs:
                    session['d'] = d
                    if eval(condition, env, session):
                        d['state'] = state2

stopping = False
while not stopping:
    # First we need to go through an authorization step.
    # The first line sent needs a username and password.
    session = {}
    sys.stdout.write('Please login\n')
    while True:
        line = sys.stdin.readline()
        if not line:
            stopping = True
            break
        parts = line.strip().split()
        if not parts:
            continue
        if parts[0] == 'login':
            username, password = parts[1:]
            if username in users:
                if checkpasswd(password, users[username]['password']):
                    sys.stdout.write('Welcome, %s\n'%username)
                    # For use in queries, add the current user and users to the session.
                    # Note: THESE MUST NEVER BE USED FOR AUTHORIZATION
                    # because the user might be able to change their value in the session.
                    session['user'] = username
                    session['users'] = list(users.keys())
                    break
        sys.stdout.write('Error during login')

    if stopping:
        break

    line = ''
    for line in sys.stdin:
        l = line.strip()
        print (l, file=sys.stderr)
        cmnd, l = l.split(maxsplit=1)
        result = None
        if cmnd == 'insert':
            # The rest of the line is a JSON document that needs storing
            oid = len(documents) + 1
            doc = eval(l, env, session)
            doc['state'] = 'initial'
            documents[oid] = doc
            execute_event('insert(%s)'%doc['type'])
            result = oid
        elif cmnd == 'delete':
            # The rest of the line is an index into the document directory that needs deleting
            oid = int(l)
            assert oid in documents, 'Object does not exist'
            del documents[oid]
            execute_event('delete(%s)'%documents[oid]['type'])
            result = 'deleted'
        elif cmnd == 'update':
            # The line should be in Python syntax and return a tuple of two items:
            # the selector for objects, and the delta. The selector can be a direct index,
            # or a generator. The delta can be a dictionary or a function yielding dicts.
            selector, delta = eval(l, env, session)
            def update_obj(obj):
                values = delta
                if callable(values):
                    values = values(obj)
                obj.update(values)
                return obj

            if isinstance(selector, dict):
                result = update_obj(selector)
            else:
                result = [update_obj(o) for o in selector]
        elif cmnd == 'get':
            # The rest of the line is a python-syntax expression
            # The expression refers to the documents as 'doc',
            # the current user is 'user', his roles are 'userroles',
            # and the user can set specific variables to specific values in the session.
            result = eval(l, env, session)
        elif cmnd == 'logout' or not cmnd:
            stopping = True
            break

        elif cmnd == 'transition':
            # Transitions are defined by:
            #   - event spec, e.g. add(<doctype>)
            #   - doctype for document on which the transition pertains
            #   - from_state, to_state
            #   - condition
            event, doctype, state1, state2, condition = l.split(maxsplit=4)
            collection = transitions
            for part in [event, doctype, state1, condition]:
                collection = collection.setdefault(part, {})
            collection = state2
            result = 'ok'

        elif cmnd == 'event':
            # Additional external events, not related to the datastructure.
            # E.g. a action executed on a specific document like 'Accept' or 'Reject'.
            result = execute_event(l)

        json.dump(result, sys.stdout)
        sys.stdout.write('\n')
        line = ''

    if not line:
        stopping = True
        break

    if stopping:
        break

sys.stdout.write('Goodby\n')
