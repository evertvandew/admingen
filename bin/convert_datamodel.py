#!/usr/bin/env python3
"""
Generate a data model from an extended CSV database.

It receives the name of the CSV database as argument, and writes the datamodel to stdout.
"""

import argparse

from admingen.data import CsvReader

parser = argparse.ArgumentParser(__doc__)
parser.add_argument('csv_database')
parser.add_argument('-d', '--delimiter', default=',')
args = parser.parse_args()


# Read the CSV database
with open(args.csv_database) as istream:
    data = CsvReader(istream, args.delimiter)

# Now write the tables and their contents to stdout as a data model
for table in data:
    print (table)