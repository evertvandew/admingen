
import sys
from urllib.parse import urlparse
from tempfile import NamedTemporaryFile
from subprocess import call
import typing
from jinja2 import Environment
from babel.numbers import format_currency
import yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper



soffice = '/opt/libreoffice6.0/program/soffice'


def readUrl(url):
    """ Generator that reads an url """
    parts = urlparse(url)
    if parts.scheme == 'http':
        raise NotImplementedError()
    if parts.scheme == 'file':
        f = open(parts.path)
    if parts.scheme == 'stdin':
        f = open(sys.stdin)

    for line in f:
        yield line

    f.close()




def moneyformat(input):
    return format_currency(input, 'EUR', locale='nl_NL.utf8')

env = Environment(autoescape=True)

env.filters['moneyformat'] = moneyformat


def render(template, fname, export_type='pdf', **kwargs):
    # Evaluate the template
    t = env.from_string(template)
    s = t.render(kwargs)
    # Store the resulting text in a temporary file
    #with NamedTemporaryFile() as f:
    with open(fname, 'w') as f:
        f.write(s)

        # Use libreoffice to make a PDF version of the text, and store it permanently
        call([soffice, '--convert-to', export_type, fname, '--headless'])

def render_stream(instream: typing.TextIO, tmplstream: typing.TextIO, outstream: typing.TextIO):
    data = yaml.load(instream, Loader=yaml.UnsafeLoader)
    assert isinstance(data, dict)

    template = tmplstream.read()

    # Evaluate the template
    t = env.from_string(template)
    s = t.render(data)

    outstream.write(s)
