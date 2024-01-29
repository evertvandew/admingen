#!/usr/bin/env python3
""" Simple script that takes an XML file and installs any components in it. """


from argparse import ArgumentParser
import os
import os.path as op
import subprocess as sp
import shutil
import glob
from admingen.xml_template import processor, Tag

def handle_Component(args, lines):
    url = args['url']
    archive = op.split(url)[-1]
    if not op.exists(archive):
        sp.run(['wget', url])
    target = args['path']
    basename, extension = op.splitext(archive)
    if extension in ['.zip', '.gz', '.tar', '.tgz']:
        shutil.unpack_archive(archive, target)
        repo_name = args.get('offset', False) or op.splitext(archive)[0]
        dirname = op.join(target, repo_name)
        files = glob.glob(dirname+'/*')
        if 'extract_only' in args:
            files = [op.join(dirname, p) for p in args['extract_only'].split(',')]
        for f in files:
            if op.isfile(f):
                relpath = op.join(target, op.relpath(f, dirname))
                shutil.copy2(f, relpath)
            else:
                subdir = op.split(f)[-1]
                shutil.copytree(f, op.join(target, subdir), dirs_exist_ok=True)
        shutil.rmtree(dirname)
    else:
        # The downloaded component is not an archive, store it directly.
        # Check that the user has not installed a simlink between the two files.
        tf = op.join(target, op.basename(archive))
        if not (op.exists(tf) and op.samefile(archive, tf)):
            print("SAMEFILE CHECK:", archive, tf)
            shutil.copy(archive, target)
    return ''


def run():
    parser = ArgumentParser()
    parser.add_argument('--file', '-f', default='')
    args = parser.parse_args()

    _ = processor({'Component': Tag('Component', handle_Component)},
                  istream=args.file, ostream=open('/dev/null', 'w'))

if __name__ == '__main__':
    run()