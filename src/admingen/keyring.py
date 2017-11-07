""" A simple keyring utility """

import os
from getpass import getpass
import os.path
import secrets
import json
import base64
import shutil
from Crypto.Cipher import AES


class DecodeError(RuntimeError): pass


def mkKey(password, salt, length=32):
    """ Create the key that is used by the Cypher for encrypting and decrypting
    """
    return (password.encode('ascii') + salt)[:length]


def writeFile(fname, password, data):
    """ Write (update) the encrypted file. Simply overwrite the whole file.
        A new salt is created for each write, so the complete file will change.
    """
    salt = secrets.token_bytes(32)
    key = mkKey(password, salt)
    cypher = AES.new(key, AES.MODE_CFB, IV='\x00'*16)
    darktext = cypher.encrypt(json.dumps(data))
    with open(fname, 'wb') as f:
        f.write(base64.b64encode(salt))
        f.write(b'\n')
        f.write(darktext)


def readFile(fname, password):
    """ Read the encrypted file.
    """
    with open(fname, 'rb') as f:
        data = f.read().split(b'\n', 1)
    salt = base64.b64decode(data[0])
    key = mkKey(password, salt)
    cypher = AES.new(key, AES.MODE_CFB, IV='\x00'*16)
    try:
        return json.loads(cypher.decrypt(data[1]))
    except UnicodeDecodeError:
        raise DecodeError('Could not decrypt keyring: probably wrong password.')


class KeyRing:
    """ File format: the first line contains a base64 encoded salt.
        Then follows the encrypted data: JSON data with key:value pairs.
    """
    def __init__(self, fname, passwd):
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
        # Make a backup to protect against file corruption due to crashes
        writeFile(self.fname+'.new', self.passwd, self.data)
        shutil.move(self.fname, self.fname+'.bak')
        shutil.move(self.fname+'.new', self.fname)


    def items(self):
        return self.data.items()
