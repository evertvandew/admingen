
import sys
from urllib.parse import urlparse
from tempfile import NamedTemporaryFile
from subprocess import call
from jinja2 import Environment
from babel.numbers import format_currency
from .parsers import fsm_model
from .dbengine import createDbModel



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


def render(template, **kwargs):
    # Evaluate the template
    t = env.from_string(template)
    s = t.render(kwargs)
    # Store the resulting text in a temporary file
    #with NamedTemporaryFile() as f:
    fname = '%s.fodt'%kwargs['factuur'].nummer
    with open(fname, 'w') as f:
        f.write(s)

        # Use libreoffice to make a PDF version of the text, and store it permanently
        call([soffice, '--convert-to', 'pdf', fname, '--headless'])


def run(db_url, model_url, query, template_url, output_url):
    """ Generate a report """
    # Read and parse the model
    ast = fsm_model.parse(readUrl(model_url))
    db, db_model = createDbModel(ast['tables'], [])

    # Connect to the database
    # Perform the query
    # Read the template
    # Substitute the query element
    # Write to the output

