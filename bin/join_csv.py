#!/usr/bin/env python3
""" A script to do a database-style join on CSV tables """

import sys
import argparse



def do_join(file_1, file_2, c1, c2):
    # First read all records for file_b, and make a lookup table
    records_2 = [l.strip().split(',') for l in file_2 if l]
    lookup = {r[c2-1]: [c for i, c in enumerate(r) if i != c2-1] for r in records_2}
    records_1 = [l.strip().split(',') for l in file_1 if l]
    # Do the actual join
    print([lookup.get(r[c1-1], []) for r in records_1])
    records = [r+lookup.get(r[c1-1], []) for r in records_1]
    # And write them to the output
    sys.stdout.write('\n'.join(','.join(r) for r in records))
    

p = argparse.ArgumentParser()
p.add_argument('file1')
p.add_argument('file2')
p.add_argument('c1', default=1)
p.add_argument('c2', default=1)
args = p.parse_args()

do_join(open(args.file1), open(args.file2), int(args.c1), int(args.c2))
