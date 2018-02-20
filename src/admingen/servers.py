
import urllib
import time
import asyncio
import json
import os, os.path
import logging
from inspect import getmembers, Signature, Parameter
from urllib.parse import urlparse
from collections import Mapping
import socket
import cherrypy
from .keyring import KeyRing, DecodeError
import admingen.htmltools as html
from .dataclasses import dataclass, asdict
from .appengine import ApplicationModel
from .db_api import the_db, sessionScope, DbTable, select, delete, Required, Set, commit, orm


# TODO: implement checking the parameters in a unix server message

class UnknownMessage(RuntimeError): pass
class FormatError(RuntimeError): pass
class RemoteError(RuntimeError): pass
class ServerError(RuntimeError):
    def __init__(self, name, msg):
        self.name = name
        RuntimeError.__init__(self, msg)

class MessageEncoder(json.JSONEncoder):
    def default(self, o):
        return o.__dict__



def decodeUnixMsg(m):
    # Let Python string conversions
    decoded = m.decode("unicode_escape")
    return json.loads(decoded)

def encodeUnixMsg(m):
    decoded = json.dumps(m, cls=MessageEncoder)
    return decoded.encode("unicode_escape")

def expose(func):
    func.exposed = True
    return func


def mkUnixServer(context, path, loop=None):
    async def handler(reader, writer):
        logging.debug('Server got a connection')
        while True:
            data = await reader.readline()
            logging.debug('Server read data: %s'%data)
            try:
                msg = decodeUnixMsg(data)
                if not isinstance(msg, list) or len(msg) != 3:
                    raise FormatError()
                func = getattr(context, msg[0], False)
                if not func or not getattr(func, 'exposed', False):
                    writer.writeline(b'ERROR: unknown function\n')
                    raise UnknownMessage(msg[0])
                args = msg[1]
                kwargs = msg[2]
                reply = [200, func(*args, **kwargs)]
            except UnknownMessage as e:
                reply = [404, 'Unknown message']
            except (SyntaxError, FormatError, json.decoder.JSONDecodeError):
                reply = [400, 'Could not decode message']
            except Exception as e:
                reply = [500, [e.__class__.__name__, str(e)]]

            logging.debug('Writing reply: %s'%reply)
            writer.write(encodeUnixMsg(reply) + b'\n')

    logging.info('Starting server on %s'%os.path.abspath(path))
    return asyncio.start_unix_server(handler, path)



def unixproxy(cls, path):
    exports = [name for name, f in getmembers(cls) if getattr(f, 'exposed', False)]

    # Wait until the server is in the air
    logging.info('Proxy listening on %s'%os.path.abspath(path))
    while not os.path.exists(path):
        time.sleep(0.1)
    logging.info('Socket file exists')

    class Proxy:
        def __init__(self):
            sock = socket.socket(socket.AF_UNIX)
            self.connected = False
            while not self.connected:
                try:
                    sock.connect(path)
                    self.connected = True
                    logging.debug('Proxy connected')
                except ConnectionRefusedError:
                    time.sleep(0.1)

            self.sock = sock
            self.buf = b''

        def __del__(self):
            logging.debug('Closing proxy socket')
            self.connected = False
            self.sock.close()

        def _read_line(self):
            assert self.connected
            while True:
                if b'\n' in self.buf:
                    i = self.buf.index(b'\n')
                    msg = self.buf[:i+1]
                    self.buf = self.buf[i+1:] if len(self.buf) > i else b''
                    return msg
                d = self.sock.recv(1024)
                logging.debug('Proxy received data: %s'%d)
                self.buf += d

        def _add_service(self, name):
            def service(*args, **kwargs):
                assert self.connected
                # pack the arguments
                data = [name, args, kwargs]
                msg = encodeUnixMsg(data)
                # Send the message and return the results
                logging.debug('Proxy sending message: %s'%msg)
                self.sock.send(msg+b'\n')
                reply = self._read_line()
                reply = decodeUnixMsg(reply)
                if reply[0] == 200:
                    return reply[1]
                elif reply[0] == 500:
                    # Raise something the application can handle
                    raise ServerError(*reply[1])
                raise RemoteError('Error when calling server: %s'%reply)
            setattr(self, name, service)

    p = Proxy()
    for n in exports:
        p._add_service(n)
    return p


Message = dataclass

def serialize(obj):
    """ Serialize a dataclass, as a JSON dictionary """
    return json.dumps(asdict(obj))

def deserialize(cls, msg):
    """ Deserialize a message into a dataclass """
    if not msg:
        return None
    data = json.loads(msg)
    return cls(**data)

def update(obj, new_data: Mapping):
    """ Update the elements in a data class """
    for k, v in new_data.items():
        setattr(obj, k, v)

def wraphandlers(cls, decorator):
    """ Decorate all exposed request handlers in a class """
    exposed = [name for name, func in getmembers(cls) if getattr(func, 'exposed', False)]
    for n in exposed:
        f = decorator(getattr(cls, n))
        f.exposed = True
        setattr(cls, n, f)


def keychain_unlocker(fname):
    """ A decorator for cherrypy server classes that adds keychain management.
        Functions in the server can be reached only after the keychain is unlocked.
        A function 'unlock' is added to the server.
    """
    def decorator(cls):
        """ Decorate the server class """
        cls.keyring = None

        def check_keyring(func):
            """ Decorator for checking if the keychain is unlocked """
            def doIt(*args, **kwargs):
                """ Check if the keychain is unlocked before handling the request """
                # whenever a user posts a form we verify that the csrf token is valid.
                if cls.keyring is None:
                    raise cherrypy.HTTPError(503, 'Service unavailable')
                return func(*args, **kwargs)
            return doIt

        def unlock(self, password=None):
            """ Let the user unlock the keychain """
            if cls.keyring:
                return cls.Page('The keyring is already unlocked')
            def submit():
                """ Called when the user submits data """
                try:
                    if password:
                        cls.keyring = KeyRing(fname, password)
                        return cls.Page('The keyring is unlocked')
                except DecodeError:
                    time.sleep(3)
                    raise cherrypy.HTTPError(401, 'No Access')
            return cls.Page(html.Title('Unlock Keyring'),
                            html.SimpleForm(html.form_input('password', 'password', 'password'),
                                       success=submit))

        wraphandlers(cls, check_keyring)

        cls.unlock = cherrypy.expose(unlock)
        return cls
    return decorator


def run_model(model: ApplicationModel):
    """ Get the configuration, and instantiate the backend server for the model.

        A simple cherrypy server with pure HTML client is created.
    """
    state_variables = model.fsmmodel.state_variables
    def createFsmHandler(name):
        # Create handlers for each FSM
        varpath = state_variables[name]
        table_name, column_name = varpath.split('.')
        table = getattr(the_db, table_name)

        baseclass = html.generateCrudCls(table, hidden=[column_name])

        class FsmHandler(baseclass):
            @expose
            def index(self):
                # Present an overview of the amount of elements in a particular state
                with sessionScope():
                    # Count the number of objects for each state
                    # TODO: Replace hardcoded name (state) with column_name
                    counts = select((o.state, orm.count(o)) for o in table)[:]
                    # Allow the user to create entities in the right states
                    return html.Page(html.Title(name),
                                     html.Lines(*['%s: %s'%c for c in counts]),
                                     html.Button('Begin een nieuwe %s'%name, 'add'))
            @expose
            def index_state(self, state):
                return baseclass.index(self, query='%s=%s'%(column_name, state))

        return FsmHandler()

    # Create the server class
    class ApplicationServer:
        @expose
        def index(self):
            # Return a selector for which FSM we want to work with
            return html.Page(html.Title('Urenregistratie'),
                             *[html.Button(fsm, fsm) for fsm in state_variables])

    for name in state_variables:
        setattr(ApplicationServer, name, createFsmHandler(name))

    with sessionScope():
        counts = select((o.state, orm.count(o)) for o in the_db.Opdracht)
        print ('Counts:', counts)

    html.runServer(ApplicationServer)
