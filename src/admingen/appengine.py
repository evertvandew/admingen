from typing import Dict, Set, List
from builtins import *  # So they can be accessed from the CuriousEnv

from pony import orm

from .parsers import fsm_model as model
from .htmltools import generateCrud
from .db_api import the_db
from dataclasses import dataclass
from .fsmengine import createFsmModel, FsmModel, Transition
from .dbengine import createDbModel

@dataclass
class ApplicationModel:
    fsmmodel: FsmModel
    db: orm.core.Database
    dbmodel: Dict[str, orm.core.EntityMeta]


class Error(RuntimeError): pass


def readconfig(stream):
    ast = model.parse(stream.read(), start='projects', whitespace=r'[ \t\r]')
    fsmmodel = createFsmModel(ast)
    fsm_names = [fsm['name'] for fsm in ast['fsms']]
    db, dbmodel = createDbModel(ast['tables'], fsm_names)

    return ApplicationModel(fsmmodel=fsmmodel,
                      db=db,
                      dbmodel=dbmodel)


def engine(model: ApplicationModel):
    """ Transitions is a msg : [transition] dictionary
        model is a table : db.Entity dictionary
    """

    def handle(msg):
        path = msg.path.strip('/').split('/')
        # The method and first part of the path show which transition is requested.
        trans = model.transitions[msg.method]
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
