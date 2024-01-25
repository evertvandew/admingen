#!/usr/bin/env python3

from argparse import ArgumentParser
from admingen.keyring import editor



def run():
    parser = ArgumentParser()
    parser.add_argument('--filename', '-f', help='Name of the keyring', default=None)

    args = parser.parse_args()

    editor(args.filename)


if __name__ == '__main__':
    run()