#!/usr/bin/env python3
""" This script does several things:

* It retrieves inline graphics from the MD file and update the associated SVG files, if necessary.
* It generates a list of dependencies for use in a Make file
* It extracts macro values from the MD file and fills them into the Latex template.

Use e.g. as:

    process_md.py -f proma_tennet.md > proma.tex; pdflatex proma.tex

"""

from argparse import ArgumentParser
import sys
from jinja2 import Template
import subprocess
import os.path
import sys


parser = ArgumentParser(__doc__)
parser.add_argument('-d', '--dependencies', action='store_true',
                    help='Generate a space-separated list of dependencies.')
parser.add_argument('-f', '--filename', default=None, help='Input file. Defaults to stdin')
parser.add_argument('-m', '--macros', action='store_true', help='Only extract the macros')
parser.add_argument('--dir', default='/home/ehwaal/Documents/templates', help='Location of template documents')
parser.add_argument('-t', '--template', default=None, help='Template file to be used.')
parser.add_argument('-i', '--intermediate', action='store_true', help='Store the intermediate results. Only when the -f option is used.')

def open_file(fname):
    if fname:
        return open(fname)
    return False


args = parser.parse_args()

infile = open_file(args.filename) or sys.stdin

# Gather the 'macros' from the text
macros = {}
body = []
for line in infile:
    if line.startswith('%%'):
        sl = line[2:].strip()
        if ' ' in sl:
            name, value = sl.split(maxsplit=1)
            macros[name.lower()] = value
        continue
    body.append(line)

if args.macros:
    print (macros)
    sys.exit(0)

# If a markdown template was defined, evaluate it before generating the latex.
if 'md_template' in macros:
    # Find the template file, either in the local directory of the template directory.
    fname = macros['md_template']
    if not os.path.exists(fname):
        fname = os.path.join(args.dir, fname)
    md_t = Template(open(fname).read())
    # Render the template, also append any text to the end.
    md_text = md_t.render(**macros) + ''.join(body)

if args.intermediate:
    if args.filename is None:
        print("-i needs the -f option", file=sys.stderr)
    else:
        with open(args.filename+'.int', 'w') as out:
            out.write(md_text)

# Filter 'body' through pandoc to turn it into latex.
#cmnd = 'pandoc -f gfm -t latex --top-level-division=chapter'
cmnd = 'pandoc -f markdown+raw_tex -t latex --top-level-division=chapter'
p = subprocess.run(cmnd, input=md_text.encode('utf8'), capture_output=True, shell=True)
#p = subprocess.run(cmnd, input=''.join(body).encode('utf8'), shell=True)
latex = p.stdout.decode('utf8')

# Look for and decode latex commands
# These are prefixed 

# Also look for the tex template
# Priority: document template, cmndline template, default.
fname = macros.get('tex_template', None) or args.template or 'report.text'
if not os.path.exists(fname):
    fname = os.path.join(args.dir, fname)
t = Template(open(fname).read())
print(t.render(body=latex, **macros))
