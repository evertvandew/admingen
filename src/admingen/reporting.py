
import sys
from .parsers import fsm_model
from .dbengine import createDbModel


def readUrl(url):
    """ Generator that reads an url """
    parts =
    if parts.scheme == 'http':
        xxxx
    if parts.scheme == 'file':
        f = open(parts.path)
    if parts.scheme == 'stdin':
        f = open(sys.stdin)

    for line in f:
        yield line

    f.close()




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

