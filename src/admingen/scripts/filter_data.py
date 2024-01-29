#!/usr/bin/env python3

import sys
import argparse
import logging

tryonce = 1
while True:
    try:
        from admingen.data import filter
        break
    except ModuleNotFoundError:
        from os.path import abspath, dirname, join
        d = abspath(join(dirname(__file__), '../src'))
        sys.path.append(d)
        assert tryonce > 0, 'Could not find admingen'
        tryonce -= 1


def run():
    #print("Arguments:", sys.argv, file=sys.stderr)
    parse = argparse.ArgumentParser()
    parse.add_argument('script')
    parse.add_argument('-d', dest='defines', action='append', default=[])
    parse.add_argument('-f', '--file', default=sys.stdin)
    parse.add_argument('-s', '--separator', default=';')
    args = parse.parse_args()
    script = open(args.script).read()
    defines_parts = [d.split('=') for d in args.defines]
    defines = {k:v for k, v in defines_parts}
    source = sys.stdin
    if isinstance(args.file, str):
        source = open(args.file)
    try:
        filter(source, script, sys.stdout, defines, delimiter=args.separator)
    except AssertionError as e:
        logging.error(e)
        sys.exit(1)


if __name__ == '__main__':
    run()