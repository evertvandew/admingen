
from typing import Dict, Set, List
import re

from .dataclasses import dataclass

@dataclass
class Transition:
    fsm: str
    start: str
    end: str


@dataclass
class FsmModel:
    # Transitions: dictionary of actions containing dicts of FSM names and transitions
    transitions: Dict[str, Dict[str, Transition]]
    # Where the current state is stored in the database
    state_variables: Dict[str, str]   # fsm name : path of variable
    # The allowed states
    states: Dict[str, List[str]]
    # The initial states
    initial: Dict[str, str]


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
    # Check that the FSM's are consistent
    return lookup


fsm_finder = re.compile(r'StateVariable\(([a-zA-Z0-9_]*)\)')

def findStateVariables(ast, names):
    # Iterate through the tables and find state variables
    statevariables = {}
    for table in ast:
        for column in table.columns:
            m = fsm_finder.search(column.details)
            if m:
                # We have a state variable
                fsm = m.group(1)
                statevariables[fsm] = '%s.%s'%(table.name, column.name)

    errors = ['No state variable found for fsm %s'%fsm
              for fsm in names if fsm not in statevariables]
    errors += ['State variable found for unknown fsm %s'%fsm
               for fsm in statevariables if fsm not in names]
    if errors:
        print ('\n'.join(errors))
        raise RuntimeError('Incorrect model')

    return statevariables

def findStates(ast):
    """ Find the different states for all FSM's """
    fsms = {}
    initial_states = {}
    for fsm in ast:
        states = set()
        for t in fsm.transitions:
            if isinstance(t['from'], list):
                states.update(t['from'])
            else:
                states.add(t['from'])
            states.add(t['to'])
        states.remove('[*]')
        # Find the initial state
        initial = [t['to'] for t in fsm.transitions if t['from'] == '[*]']
        assert len(initial) == 1, 'Wrong number of start states for FSM %s'%fsm.name
        initial_states[fsm.name] = initial[0]
        fsms[fsm.name] = states
    return fsms, initial_states

def createFsmModel(ast):
    fsm_names = [f.name for f in ast['fsms']]
    states, initial = findStates(ast['fsms'])
    return FsmModel(transitions=determineMsgHandlers(ast['fsms']),
                    state_variables=findStateVariables(ast['tables'], fsm_names),
                    states=states,
                    initial=initial)