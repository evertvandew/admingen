#!/usr/bin/env python3
""" Download a set of meetings from google and output them in different formats.

The script needs configuration with e.g. the ID of the calendar as  known by Google.
These details can also be read from a configuration file.
"""

import datetime
import sys
import argparse
import requests
import admingen.data.ical_parser as icp
from admingen.data import CsvWriter
from io import StringIO

parser = argparse.ArgumentParser(__doc__)
parser.add_argument('--config_file', '-c')
parser.add_argument('--range', '-r', help='The start and end date. Format: yyyymmdd-yyyymmdd')
parser.add_argument('--url', '-u')

def get_calendar_meetings(url, range):
    if url:
        result = requests.get(url)
        if result.status_code != 200:
            print('Could not download data from google', file=sys.stderr)
            sys.exit(1)
        f = StringIO(result.text)
    else:
        f = sys.stdin

    tp_start = datetime.datetime.strptime(range.split('-')[0], '%Y%m%d')
    tp_end = datetime.datetime.strptime(range.split('-')[1] + ' 235959', '%Y%m%d %H%M%S')

    parser = icp.ical_reader(f, tp_start, tp_end)

    meetings = [m for m in parser]

    # Use only a selection of the columns
    columns = 'DTSTART DTEND SUMMARY DESCRIPTION'.split()
    # Only use meetings with all columns
    meetings = [meeting for meeting in meetings if all(k in meeting for k in columns)]
    # Use only a selection of the columns
    meetings = [{k: meeting[k] for k in columns} for meeting in meetings]

    return meetings

if __name__ == '__main__':
    args = parser.parse_args()

    if not args.range:
        now = datetime.datetime.now()
        args.range = '-'.join([now.strftime('%Y0101'), now.strftime('%Y%m%d')])

    meetings = get_calendar_meetings(args.url, args.range)
    CsvWriter(sys.stdout, {'Meetings': meetings})
