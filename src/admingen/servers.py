
import time
import asyncio
import json
import os, os.path
from inspect import getmembers
from urllib.parse import urlparse
import socket
import cherrypy
from .keyring import KeyRing, DecodeError
from .htmltools import SimpleForm, Title, form_input


class UnknownMessage(RuntimeError): pass
class FormatError(RuntimeError): pass
class RemoteError(RuntimeError): pass

def decodeUnixMsg(m):
    # Let Python string conversions
    decoded = m.decode("unicode_escape")
    return json.loads(decoded)

def encodeUnixMsg(m):
    decoded = json.dumps(m)
    return decoded.encode("unicode_escape")

def expose(func):
    func.exposed = True
    return func


def mkUnixServer(context, path, loop=None):
    async def handler(reader, writer):
        while True:
            data = await reader.readline()
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

            writer.write(encodeUnixMsg(reply) + b'\n')

    return asyncio.start_unix_server(handler, path)



def unixproxy(cls, path):
    exports = [name for name, f in getmembers(cls) if getattr(f, 'exposed', False)]

    # Wait until the server is in the air
    while not os.path.exists(path):
        time.sleep(0.1)

    class Proxy:
        def __init__(self):
            sock = socket.socket(socket.AF_UNIX)
            sock.connect(path)
            self.sock = sock
            self.buf = b''

        def __del__(self):
            self.sock.close()

        def _read_line(self):
            while True:
                if b'\n' in self.buf:
                    i = self.buf.index(b'\n')
                    msg = self.buf[:i+1]
                    self.buf = self.buf[i+1:] if len(self.buf) > i else b''
                    return msg
                d = self.sock.recv(1024)
                self.buf += d

        def _add_service(self, name):
            def service(*args, **kwargs):
                # pack the arguments
                data = [name, args, kwargs]
                msg = encodeUnixMsg(data)
                # Send the message and return the results
                self.sock.send(msg+b'\n')
                reply = self._read_line()
                reply = decodeUnixMsg(reply)
                if reply[0] == 200:
                    return reply[1]
                raise RemoteError('Error when calling server: %s'%reply)
            setattr(self, name, service)

    p = Proxy()
    for n in exports:
        p._add_service(n)
    return p


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
            return cls.Page(Title('Unlock Keyring'),
                            SimpleForm(form_input('password', 'password', 'password'),
                                       success=submit))

        wraphandlers(cls, check_keyring)

        cls.unlock = cherrypy.expose(unlock)
        return cls
    return decorator

