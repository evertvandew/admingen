import urllib
import time
import asyncio
import json
import os, os.path
import logging
import sys
import threading
import tty, termios
from inspect import getmembers, signature, Parameter
from urllib.parse import urlparse
from collections import Mapping
import socket
import cherrypy
from .keyring import KeyRing, DecodeError
import admingen.htmltools as html
from dataclasses import dataclass, asdict, fields, is_dataclass
from .appengine import ApplicationModel
from .db_api import the_db, sessionScope, DbTable, select, delete, Required, Set, commit, orm

if 'win' in sys.platform:
    logging.error('This software is not intended to be run on amature platforms')


# TODO: implement checking the parameters in a json unix server message

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


welcome = b'''Welcome to %s
protocol 1.0
Type "help" for useful information'''


class aioStdinReader:
    def __init__(self, loop):
        self.th = threading.Thread(target=self._run)
        self.th.daemon = True
        self.th.start()
        self.q = asyncio.Queue()
        self.buf = b''
        self._loop = loop

    def _run(self):
        fd = sys.stdin.fileno()
        try:
            # Let lines also end when the ESC key is pressed
            flags = termios.tcgetattr(fd)
            flags[tty.CC][termios.VEOL] = 0x1b
            termios.tcsetattr(fd, termios.TCSANOW, flags)
        except termios.error:
            pass
        while True:
            # Do blocking reads at os level to avoid built-in buffering
            d = os.read(0, 4100)
            self._loop.call_soon_threadsafe(self.q.put_nowait, d)

    async def readline(self, seperator=b'\n'):
        while seperator not in self.buf:
            data = await self.q.get()
            self.buf += data
        result, self.buf = self.buf.split(b'\n', 1)
        return result


class aioStdoutWriter:
    def write(self, m):
        sys.stdout.write(m.decode('utf8'))
        sys.stdout.flush()


def arguments(parameters):
    """ Generator for the arguments given to a function.
        Recursively descends into dataclasses.
    """

    def recurse(prefix, dclass):
        for field in fields(dclass):
            name = '.'.join([prefix, field.name])
            if is_dataclass(field.type):
                yield from recurse(name, field.type)
            yield name, field.type

    for name, p in parameters.items():
        a = p.annotation
        if a == p.empty or a == str:
            yield (name, None)
        elif is_dataclass(a):
            yield from recurse(name, a)
        else:
            yield name, a


def castArguments(kwargs, parameters):
    """ Handle arguments given through the CLI interface and cast
        them to the proper types and objects.
    """
    result = {}
    for name, p in parameters.items():
        a = p.annotation
        if is_dataclass(a):
            r = {}
            for f in fields(a):
                value = kwargs['%s.%s' % (name, f.name)]
                try:
                    if f.type == str:
                        r[f.name] = value.decode('utf8')
                    else:
                        r[f.name] = f.type(value)
                except Exception as e:
                    raise FormatError(
                        'Could not cast value %s to type %s' % (value, f.type.__name__))
            result[name] = a(**r)
        else:
            value = kwargs[name]
            if name not in kwargs:
                continue
            try:
                result[name] = a(value)
            except Exception as e:
                raise FormatError('Could not cast value %s to type %s' % (value, a.__name__))
    return result


def mkUnixServer(context, path, loop=None):
    exports = [name for name, f in getmembers(context) if getattr(f, 'exposed', False)]

    def printHelp(context, writer):
        writer.write(b'The following functions are provided:\n')
        for f in exports:
            doc = getattr(context, f).__doc__ or ''
            msg = (f + ': ' + doc + '\n').encode('utf8')
            writer.write(msg)

    def json_command_handler(reader, writer):
        """ Generator for parsing data """
        while True:
            data = yield None
            logging.debug('Server read data: %s' % data)
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
                logging.exception('Server exception')
                reply = [500, [e.__class__.__name__, str(e)]]

            logging.debug('Writing reply: %s' % reply)
            writer.write(encodeUnixMsg(reply) + b'\n')

    def cli_command_handler(reader, writer):
        writer.write(welcome % context.__class__.__name__.encode('utf8'))
        while True:
            writer.write(b'\n> ')
            # Read a command
            data = yield None
            cmnd = data.strip().lower().decode('utf8')
            # Handle the built-in command (help, json)
            if cmnd == 'help':
                printHelp(context, writer)
                continue
            if cmnd == 'json':
                # Switch to the JSON protocol
                writer.write(b'OK\n')
                yield json_command_handler(reader, writer)
            func = getattr(context, cmnd, False)
            if func and getattr(func, 'exposed', False):
                sig = signature(func)
            else:
                writer.write(b'ERR: Unknown command %s\n' % cmnd.encode('utf8'))
                continue

            # Read the arguments for the command
            # The escape key will break
            escape = False
            kwargs = {}
            for name, paramtype in arguments(sig.parameters):
                writer.write(b'%s: ' % name.encode('utf8'))
                value = yield None
                # Handle the escape key
                if b'\x1b' in value:
                    escape = True
                    break
                if value:
                    kwargs[name] = value.rstrip(b'\n')

            # Check if the escape key was pressed.
            if escape:
                continue

            try:
                kwargs = castArguments(kwargs, sig.parameters)
            except FormatError as e:
                writer.write(b'ERR: %s' % str(e).encode('utf8'))
                continue

            # The parameters have been given, now call the function
            try:
                result = func(**kwargs)
            except:
                logging.exception('exception occured in the server')
                writer.write(b'ERR error occured in the server')
                continue

            if result is None:
                result = b'OK'
            elif isinstance(result, str):
                result = result.encode('utf8')

            writer.write(bytes(result) + b'\n')

    async def handler(reader, writer):
        print('CONNECTION')
        logging.debug('Server got a connection')
        # Write the welcome message
        writer.write(welcome % context.__class__.__name__.encode('utf8'))
        protocol = cli_command_handler(reader, writer)
        protocol.send(None)
        while True:
            while True:
                data = await reader.readline()
                print('DATA', data)
                logging.debug('server read data: %s' % data)
                switch = protocol.send(data)
                if switch is not None:
                    protocol = switch
                    protocol.send(None)

    logging.info('Starting server on %s' % os.path.abspath(path))
    return asyncio.start_unix_server(handler, path)


# Fool the idea's to think this function returns the cls itself, not some mystery object
def unixproxy(cls, path):
    exports = [name for name, f in getmembers(cls) if getattr(f, 'exposed', False)]

    # Wait until the server is in the air
    logging.info('Proxy listening on %s' % os.path.abspath(path))
    while not os.path.exists(path):
        time.sleep(0.1)
    logging.info('Socket file exists')

    class Proxy:
        def __init__(self):
            self.buf = b''
            self.sock = None
            self.connected = False
            self._connect()

        def __del__(self):
            logging.debug('Closing proxy socket')
            self.connected = False
            self.sock.close()

        def _connect(self):
            if self.sock is not None:
                try:
                    self.sock.close()
                except:
                    pass
            self.connected = False
            sock = socket.socket(socket.AF_UNIX)
            while not self.connected:
                try:
                    sock.connect(path)
                    self.connected = True
                    logging.debug('Proxy connected')
                except ConnectionRefusedError:
                    time.sleep(0.1)

            self.sock = sock

            # Set the protocol to JSON mode
            sock.send(b'json\n')
            # Read the rubbish intended for humans...
            while True:
                msg = sock.recv(4096)
                if b'OK\n' in msg:
                    break

        def _read_line(self):
            assert self.connected
            while True:
                if b'\n' in self.buf:
                    i = self.buf.index(b'\n')
                    msg = self.buf[:i + 1]
                    self.buf = self.buf[i + 1:] if len(self.buf) > i else b''
                    return msg
                d = self.sock.recv(1024)
                logging.debug('Proxy received data: %s' % d)
                if not d:
                    self.sock.close()
                    self.connect()
                self.buf += d

        def _add_service(self, name):
            def service(*args, **kwargs):
                assert self.connected
                # pack the arguments
                data = [name, args, kwargs]
                msg = encodeUnixMsg(data)
                # Send the message and return the results
                logging.debug('Proxy sending message: %s' % msg)
                self.sock.send(msg + b'\n')
                reply = self._read_line()
                reply = decodeUnixMsg(reply)
                if reply[0] == 200:
                    return reply[1]
                elif reply[0] == 500:
                    # Raise something the application can handle
                    raise ServerError(*reply[1])
                raise RemoteError('Error when calling server: %s' % reply)

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
                    tbl = html.PaginatedTable(None,
                                              counts,
                                              ['Toestand', 'Aantal'],
                                              lambda data: 'index_state?state=%s' % data[0])
                    return html.Page(html.Title(name),
                                     tbl,
                                     html.Button('Begin een nieuwe %s' % name, 'add'))

            @expose
            def index_state(self, state):
                return baseclass.index(self, query='%s="%s"' % (column_name, state), add=False)

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
        print('Counts:', counts)

    html.runServer(ApplicationServer)
