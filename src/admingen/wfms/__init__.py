"""
Tools for creating a Work Flow Management System.

The workflow is defined by:
* A set of InfoType definitions, which define data structures.
* A set of Document definitions that contain these InfoTypes.
* A database of instances of these documents.
* A set of processes that indicate for each document, how it should be processed further.
* A set of users and their relation to these processes.

Each document is stored in a self-descriptive way, so that if in the future the definitions change,
old documents can still be used.

The WFMS is supposed to work as a component inside a Flask website.
"""


"""
Design decisions:
* For now, the info types are defined in Python "typing" syntax.
* Each document is stored with a header containing its meta data.
"""


from dataclasses import dataclass
from typing import Self, Tuple, List, Dict
from datetime import datetime
from admingen.gui.gui_generators import generateAutoEditor
from admingen.gui.specification import RESTDataSource
from admingen.gui.dynamic_html_renderer import FlaskClientSide
import flask

@dataclass
class db_reference:
    url: str
    id: int
    text: str

@dataclass
class DocumentMetadata:
    document_type: db_reference
    creation_datetime: datetime
    created_by: db_reference
    modification_datetime: datetime
    modified_by: db_reference
    acceptance_datetime: datetime
    accepted_by: db_reference
    status: str
    version: int

@dataclass
class InformationMetadata:
    information_type: db_reference
    data_description: str

class EntitySource:
    def getEntities(self):
        raise NotImplementedError()


def serve_page(app, url, html):
    print('Handling:', url)
    app.route(url, methods=['GET'])
    def func():
        return html

def add_handlers(app, context, entity_source, prefix='/wfms'):
    """ Add handlers to the application for editing the entities """
    renderer = FlaskClientSide()
    specs = []
    for entity in entity_source.getEntities():
        datasource = RESTDataSource(entity.__name__, '/data', entity.__name__)
        spec = generateAutoEditor(entity, datasource, {}, prefix)
        specs.append(spec)
        renderer.render(spec)
    pages = renderer.files

    @app.route(f'{prefix}/<entity>', methods=['GET'])
    def index_forwarder(entity):
        return flask.redirect(f'{prefix}/{entity}/index.html', code=302)

    @app.route(f'{prefix}/<entity>/<action>', methods=['GET'])
    def wfms_handler(entity, action):
        path = f'{prefix}/{entity}/{action}'
        if path in pages:
            return flask.make_response(pages[path], 200)
        return flask.make_response('Not Found', 404)
