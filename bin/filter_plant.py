#!/usr/bin/env python3.9
""" This script runs the input file though plant_uml, and then replaces the plant
    diagrams with a markdown reference to the generated image.
"""

import sys
import subprocess
import argparse


p = argparse.ArgumentParser()
p.add_argument('inputs', nargs='*', default=[])

args = p.parse_args()

files = args.inputs if args.inputs else [sys.stdin]

def replace_diagrams(data):
    result = []
    in_diagram = False
    for count, line in enumerate(data.split(b'\n')):
        if line.strip().startswith(b'@startuml'):
            in_diagram = True
            parts = line.strip().split()
            if len(parts) == 1:
                raise RuntimeError(b"No name for diagram, line %i."%count)
            name = parts[1]
            # Write the relevant markdown
            replacement = b"![%b](%b.png)"%(name, name)
            result.append(replacement)
        if not in_diagram and not line.strip().startswith(b'//'):
            result.append(line)
            
        if line.strip().startswith(b'@enduml'):
            in_diagram = False
    return b'\n'.join(result)
            

for fname in files:
    # Pipe the data through plantuml
    rc = subprocess.run(f'plantuml -tpng {fname}', shell=True)
    if rc.returncode:
        print("An error occurred in plantuml", file=sys.stderr)
        sys.exit(rc.returncode)
    
    # Replace the plant diagrams with markdown constructs
    with open(fname, 'rb') as i:
        data = i.read()
    filtered = replace_diagrams(data)
    sys.stdout.buffer.write(filtered)
