
import time
from inspect import getmembers
import cherrypy
from .keyring import KeyRing, DecodeError
from .htmltools import SimpleForm, Title, Password, String


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
                            SimpleForm(String('password', 'password'),
                                       success=submit))

        wraphandlers(cls, check_keyring)

        cls.unlock = cherrypy.expose(unlock)
        return cls
    return decorator

