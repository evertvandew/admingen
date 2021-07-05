#!/usr/bin/env python3

import argparse
import subprocess
import os.path

ap = argparse.ArgumentParser()
ap.add_argument('project', help='Name of the project')
ap.add_argument('component', help='Component for which to deploy')
ap.add_argument('-d', '--description', default='Descriptive name of the project')
ap.add_argument('-u', '--user', default='', help="User name to use, defaults to project name")
ap.add_argument('-s', '--service_name', default='', help='internet name of the service to be exposed.')

args = ap.parse_args()


def deploy_service(args):
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


def deploy_nginx(args):
    """ Install the configuration for serving this site through NGINX"""
    service_name = args.service_name or args.project
    if '.' not in service_name:
        service_name = service_name + '.nl'
    templ = f"""server {{

        root /var/www/html;

        # Add index.php to the list if you are using PHP
        index index.html index.htm index.nginx-debian.html;
    server_name www.${service_name} ${service_name}; # managed by Certbot


        location / {{ try_files $uri @${project}_application; }}
        location @${project}_application {{
                include uwsgi_params;
                uwsgi_pass unix:/home/${user}/var/run/${project}.s;
        }}

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/${service_name}/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/${service_name}/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot


    # Redirect non-https traffic to https.
    if ($scheme != "https") {{
        return 301 https://$host$request_uri;
    }} # managed by Certbot
}} 
"""
    fname = f'{project}.nginx'
    with open(fname, 'w') as out:
        out.write(templ)


action = {'service': deploy_service,
          'nginx': deploy_nginx}[args.component]

action(args)
