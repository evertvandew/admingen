
import smtplib
from urllib.parse import urlparse
import markdown
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate


SSL_SMTP_SCHEMES = ['smtps', '+ssl']

testmode = False


class DummyClient:
    msgs = []

    def sendmail(*args):
        DummyClient.msgs.append(args)



def mkclient(url, user=None, password=None):
    if testmode:
        return DummyClient

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

def constructMailMd(md_msg, **headers):
    """ Construct an email from a MarkDown text, and add headers. """
    # TODO: Add support for multiple recipients
    # We are using the old API for constructing emails:
    # the new one does not encode PDF attachments correctly.

    outer = MIMEMultipart()
    for key, value in headers.items():
        outer[key] = value

    outer['Date'] = formatdate(localtime=True)
    html_msg = markdown.markdown(md_msg)

    # parts = [': '.join(h) for h in zip(headers, details)]
    text_parts = MIMEMultipart('alternative')
    msg_plain = MIMEText(md_msg)
    msg_html = MIMEText(html_msg, 'html')
    text_parts.attach(msg_plain)
    text_parts.attach(msg_html)
    outer.attach(text_parts)

    return outer

