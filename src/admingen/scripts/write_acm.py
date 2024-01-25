#!/usr/bin/env python3

import sys
import json
import os.path
from admingen.xml_template import processor, data_models, default_generators, Tag, table_acm

from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument('--input', '-i', default=sys.stdin)
args = parser.parse_args()

# Extract the datamodel from the XML file.

acm = {}
current_page_context = dict(headers='', title='admingen', heading='', footer='', acm='user,editor,administrator')

def handle_Page(args, lines):
    """ Handle the ACM parameters for each page """
    url = args['url']
    acm[url.strip('/')] = args.get('acm', current_page_context['acm'])
    # for index, add alternative paths the browser will try in resolving this path
    if os.path.basename(url) in ['index.html', 'index.htm']:
        acm[os.path.dirname(url).strip('/')] = args.get('acm', current_page_context['acm'])
    return ''

def handle_PageContextValue(args, lines):
    """ Let the user modify a value in the page context.
        This value is used for all subsequent pages.
    """
    assert 'name' in args
    current_page_context[args['name']] = lines
    return ''

def handle_QueryAcm(_args, lines):
    for line in lines.splitlines():
        line = line.strip()
        if not line:
            continue
        url, roles = [l.strip() for l in line.split(':')]
        acm[url.strip('/')] = roles
    return ''

def run():
    generators = default_generators.copy()
    generators.update(
        Page=Tag('Page', handle_Page),
        PageContextValue=Tag('PageContextValue', handle_PageContextValue),
        QueryAcm=Tag('QueryAcm', handle_QueryAcm)
    )
    _ = processor(generators, istream=args.input, ostream=open('/dev/null', 'w'))

    # Add the ACM details for accessing the data tables
    for db, db_details in data_models.items():
        for table, table_def in db_details.items():
            if isinstance(table_def, dict) and table in table_acm:
                acm['data/%s'%table] = table_acm[table]

    # Write the ACM table
    for k, v in acm.items():
        print(f'{k}:{v}')


if __name__ == '__main__':
    run()