"""
Place a Command-Line Interface on a Python function.
"""
import sys
import inspect
from decimal import Decimal
from datetime import date, datetime


istream = 'istream'
ostream = 'ostream'



def mkIstream(fname):
    if fname == '-':
        return sys.stdin
    return open(fname, 'r')

def mkOstream(fname):
    if fname == '-':
        return sys.stdout
    return open(fname, 'w')


conv_lookup = {istream: mkIstream,
               ostream: mkOstream,
               Decimal: Decimal,
               str: lambda x: x,
               date: lambda x: date.strptime(x, '%Y%m%d'),
               int: int
               }


def generate(func):
    """ Run a function using the arguments supplied in the command line.
    If the function returns a 'True' value, it is assumed an error occurred.
    """
    sig = inspect.signature(func)
    args = []
    for par, value in zip(sig.parameters.values(), sys.argv[1:]):
        converter = conv_lookup[par.annotation]
        args.append(converter(value))

    result = func(*args)
    if result:
        print(result)
        sys.exit(1)
    sys.exit(0)
