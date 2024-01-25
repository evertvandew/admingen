#!/usr/bin/env python3
# Script that reads data (in JSON form) from stdin or a file, reads a template, and
# generate an output file.
# The template is intended to be in jinja format.

import sys
import argparse
from admingen.reporting import render_stream



def run():
    parse = argparse.ArgumentParser()
    parse.add_argument('template')
    args = parse.parse_args()
    render_stream(sys.stdin, open(args.template), sys.stdout)

if __name__ == '__main__':
    run()
