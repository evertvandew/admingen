import urllib
import time
import asyncio
import json
import os, os.path
from inspect import getmembers, Signature, Parameter
from urllib.parse import urlparse
import socket
import cherrypy
from .keyring import KeyRing, DecodeError
from .htmltools import SimpleForm, Title, form_input


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
            except Exception as e:
                reply = [500, [e.__class__.__name__, str(e)]]

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
            connected = False
            while not connected:
                try:
                    sock.connect(path)
                    connected = True
                except ConnectionRefusedError:
                    time.sleep(0.1)

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
                elif reply[0] == 500:
                    # Raise something the application can handle
                    raise ServerError(*reply[1])
                raise RemoteError('Error when calling server: %s'%reply)
            setattr(self, name, service)

    p = Proxy()
    for n in exports:
        p._add_service(n)
    return p


def Message(cls):
    """
        Decorate a class to turn it into a message.
        All annotated members are assumed to be part of the message.
     """

    # Make a signature from the annotations to use in the constructor
    params = [Parameter(n, Parameter.POSITIONAL_OR_KEYWORD,
                        default=getattr(cls, n) if hasattr(cls, n) else Parameter.empty,
                        annotation=a) for n, a in cls.__annotations__.items()]
    sig = Signature(params)

    def constructor(self, *args, **kwargs):
        """ Generate a constructor for the Message """
        ba = sig.bind(*args, **kwargs)
        self.__dict__.update(ba.arguments)

    cls.__init__ = constructor

    return cls


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




def oauth_accesstoken(cls, login_url, redirect_uri, token_url=None):
    """ Decorator to add tools to handle OAuth2 authentication """

    def binquote(value):
        """
        We use quote() instead of urlencode() because the Exact Online API
        does not like it when we encode slashes -- in the redirect_uri -- as
        well (which the latter does).
        """
        return urllib.parse.quote(value.encode('utf-8'))

    def getAccessToken(client_id, client_secret, code):
        params = {'code': code,
                  'client_id': binquote(client_id),
                  'grant_type': 'authorization_code',
                  'client_secret': binquote(client_secret),
                  'redirect_uri': binquote(redirect_uri)}
        response = request(token_url, method='POST', params=params)
        return response

    def request(*args, **kwargs):
        # Check if the token parameter is set
        if 'token' in kwargs:
            return func(*args, **kwargs)
        # Check if the OAUTH code was provided
        if 'code' in kwargs:
            print ('URL:', cherrypy.url())
            token = getAccessToken(kwargs['code'])
            kwargs['token'] = token['access_token']
            return func(*args, **kwargs)
        # Otherwise let the user login and get the OAUTH token.
        raise cherrypy.HTTPRedirect("https://start.exactonline.nl/api/oauth2/auth?client_id=45e63a87-5943-4163-ab90-ccb23a738ad4&redirect_uri=https://vandewaal.xs4all.nl:13958&response_type=code&force_login=0")
    cls.oauth_code = request
    return cls