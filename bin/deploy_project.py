#!/usr/bin/env python3

import argparse
import subprocess
import os.path

ap = argparse.ArgumentParser()
ap.add_argument('project', help='Name of the project')
ap.add_argument('-d', '--description', default='Descriptive name of the project')
ap.add_argument('-u', '--user', default='', help="User name to use, defaults to project name")

args = ap.parse_args()

# Create a service file for this project.
# We use a template
templ = f"""[Unit]
Description=Start server voor {args.description or args.project} service

[Service]
Type=simple
User={args.user or args.project}
Group=www-data
ExecStart=/usr/bin/make deploy
WorkingDirectory=/home/{args.user or args.project}/{args.project}
Restart=always
RestartSec=3
"""

# Write the service file
fname = f'{args.project}.service'
with open(fname, 'w') as out:
    out.write(templ)

# Install and activate the service file
cmnds = f"""sudo systemctl daemon-reload
sudo systemctl enable {os.path.abspath(fname)}
sudo systemctl start {args.project}.service""".splitlines(keepends=False)


for cmnd in cmnds:
    subprocess.run(cmnd.split())
