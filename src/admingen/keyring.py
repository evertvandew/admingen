""" A simple keyring utility """

import os
from getpass import getpass
import os.path
import secrets
import base64
import shutil
from Crypto.Cipher import AES
import json
import logging
import socket

from admingen.util import loads, dumps


VERSION = 1

class DecodeError(RuntimeError): pass


def mkKey(password, salt, length=32):
    """ Create the key that is used by the Cypher for encrypting and decrypting
    """
    return (password.encode('ascii') + salt)[:length]


def writeFile(fname, password, data):
    """ Write (update) the encrypted file. Simply overwrite the whole file.
        A new salt is created for each write, so the complete file will change.
    """
    # TODO: investigate if it would be better to keep the same salt
    salt = secrets.token_bytes(32)
    key = mkKey(password, salt)
    cypher = AES.new(key, AES.MODE_CFB, IV='\x00'*16)
    darktext = cypher.encrypt(dumps(data))
    with open(fname, 'wb') as f:
        f.write(b'%i\n'%VERSION)
        f.write(base64.b64encode(salt))
        f.write(b'\n')
        f.write(darktext)


def readFile(fname, password):
    """ Read the encrypted file.
    """
    logging.debug('Reading keyring %s'%fname)
    with open(fname, 'rb') as f:
        data = f.read().split(b'\n', 2)
    version = int(data[0])
    salt = base64.b64decode(data[1])
    key = mkKey(password, salt)
    cypher = AES.new(key, AES.MODE_CFB, IV='\x00'*16)
    try:
        txt = cypher.decrypt(data[2])
        return loads(txt)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise DecodeError('Could not decrypt keyring: probably wrong password.')


class KeyRing:
    """ File format: the first line contains a version number.
        The second line contains a base64 encoded salt.
        Then follows the encrypted data: JSON data with key:value pairs.
    """
    theKeyring = None
    def __init__(self, fname=None, passwd=None):
        if fname is passwd is None:
            # This is a memory-only test keyring
            self.data = {}
        else:
            # Get a password
            passwd = passwd or getpass('Keyring Password:')
            # Try opening the file if it exists, create it if it doesn't
            if not os.path.exists(fname):
                writeFile(fname, passwd, {})
            # Read the data
            self.data = readFile(fname, passwd)
        self.passwd = passwd
        self.fname = fname

    def __getitem__(self, item):
        return self.data.get(item, None)

    def __setitem__(self, key, value):
        # Only write when actually changed
        if self[key] == value:
            return
        self.data[key] = value
        self.update_file()

    def __delitem__(self, key):
        if key not in self.data:
            return
        del self.data[key]
        self.update_file()

    def update_file(self):
        if self.fname:
            # Make a backup to protect against file corruption due to crashes
            logging.debug('Writing to keyring %s' % self.fname)
            writeFile(self.fname + '.new', self.passwd, self.data)
            shutil.move(self.fname, self.fname + '.bak')
            shutil.move(self.fname + '.new', self.fname)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __iter__(self):
        return iter(self.keys())

    def items(self):
        return self.data.items()
    def keys(self):
        return self.data.keys()

    @staticmethod
    def setTheKeyring(ring):
        KeyRing.theKeyring = ring

    @staticmethod
    def open_from_socket(fname, server_address =  './opener.sock'):

        try:
            os.unlink(server_address)
        except OSError:
            if os.path.exists(server_address):
                raise

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        # Bind the socket to the port
        print('starting up on %s' % server_address)
        sock.bind(server_address)

        # Listen for incoming connections
        sock.listen(1)

        while True:
            # Wait for a connection
            print('waiting for a connection')
            connection, client_address = sock.accept()
            try:
                connection.send(b'Welcome to KeyRing\n')

                # Receive the data in small chunks and retransmit it
                while True:
                    data = connection.recv(1024)
                    if data:
                        data = data.strip().decode('utf8')
                        # Try to open the keyring using this password
                        try:
                            keyring = KeyRing(fname, data)
                            connection.send(b'Password accepted, thank you.\n')
                            return keyring
                        except DecodeError:
                            connection.send(b'Sorry, try again\n')
                    else:
                        break

            finally:
                # Clean up the connection
                connection.close()


def editor(fname=None):
    """ A simple CLI interface for bootstrapping / maintaining keyrings """
    fname = fname or input('Filename : ')
    password = input('Password : ')
    keyring = KeyRing(fname, password)

    print ('\n'.join(['%s = %s'%(k, keyring[k]) for k in sorted(keyring.keys())]))

    while True:
        key = input('Enter key to add / change or enter to exit : ')
        if not key:
            return
        print ('Current value: ', keyring[key])
        value = input('Enter new value or enter to leave unchanged : ')
        if value:
            # See if this is json-encoded data
            try:
                v = json.loads(value)
                keyring[key] = v
            except json.decoder.JSONDecodeError:
                print ("That was not proper JSON!")


if __name__ == '__main__':
    # If called from the command line, run a simple command-line editor for keyrings
    editor()
