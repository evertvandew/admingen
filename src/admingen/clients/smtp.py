
import smtplib
from urllib.parse import urlparse

SSL_SMTP_SCHEMES = ['smtps', '+ssl']

def mkclient(url, user=None, password=None):
    if not '/' in url:
        # If there is no slash in the url, assume it is just the hostname
        url = '//' + url

    parts = urlparse(url)
    host, port = parts.netloc, 0

    if ':' in host:
        host, port = host.split(':')
        port = int(port)

    # A secure connection MUST BE USED when a password is set.
    if any(scheme in parts.scheme for scheme in SSL_SMTP_SCHEMES) \
        or password:
        client = smtplib.SMTP_SSL(host, port)
    else:
        client = smtplib.SMTP(host, port)

    if user:
        client.login(user, password)

    return client
