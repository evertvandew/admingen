
import os, os.path
import datetime
import bcrypt
from urllib.parse import urlparse
import re
from collections import namedtuple
from enum import IntEnum

import sqlite3
from pony import orm


VERSION = 3


SystemStates = IntEnum('SystemStates', 'Start LoadingData GeneratingPDF PDFCreated')


def password2str(value):
    salt = bcrypt.gensalt()
    hash = bcrypt.hashpw(value, salt)
    return hash

def checkpasswd(clear, hashed):
    return bcrypt.checkpw(clear, hashed)

def ispwencrypted(p):
    return bool(re.match(r'^\$2a\$\d\d\$', p))

class Email(str):
    pass

class Role(str):
    @staticmethod
    def options():
        return ['Admin', 'User']

class Password(str):
    pass

class ImagePath(str):
    pass

###############################################################################
## The elements stored in the database
db = orm.Database()

class DbaseVersion(db.Entity):   #pylint:disable=W0232
    ''' Stores the version number of the database. '''
    version = orm.Required(int)


class SmtpDetails(db.Entity):
    name = orm.Required(str)
    smtphost=orm.Required(str)
    user=orm.Required(str)
    password=orm.Required(str)
    organisations=orm.Set(lambda: Organisation)


class Organisation(db.Entity):
    name = orm.Required(str, unique=True)
    description = orm.Required(str)
    mailfrom=orm.Required(str)
    gift_accounts = orm.Required(str)
    consolidated = orm.Optional(bool, default=True)
    template = orm.Optional(orm.LongStr, default='')
    mail_body = orm.Optional(orm.LongStr, default='')
    admin_email = orm.Required(Email)
    exact_division = orm.Required(int)
    admin_id = orm.Required(int)
    logo = orm.Optional(ImagePath)
    smtp_details=orm.Optional(SmtpDetails)
    status = orm.Required(int, default=SystemStates.Start.value)
    period_start = orm.Optional(datetime.datetime)
    period_end   = orm.Optional(datetime.datetime)
    people = orm.Set(lambda:User)       # The lambda is evaluated when User is in scope.


class User(db.Entity):
    name = orm.Required(str, unique=True)
    fullname = orm.Required(str)
    password = orm.Optional(Password)
    role  = orm.Required(Role)
    email = orm.Required(str)
    church = orm.Optional(Organisation)



def updatequeries(queries):
    def doIt(cursor):
        for q in queries:
            cursor.execute(q)
    return doIt

DbUpdate = namedtuple('DbUpdate', ['oldversion', 'newversion', 'update'])

dbupdates = [DbUpdate(1, 2, updatequeries([
    'ALTER TABLE organisation ADD COLUMN consolidated INT DEFAULT 1',
    'ALTER TABLE organisation ADD COLUMN gift_accounts TEXT DEFAULT "8000 8050 8100 8150 8200 8800 8900 8990 8991"',
                                         ])),
             DbUpdate(2, 3, updatequeries([
     'ALTER TABLE organisation ADD COLUMN mailfrom TEXT DEFAULT "overzichten@lifeconnexion.nl"']))
             ]


def updateDb(path):
    if os.path.exists(path):
        conn = sqlite3.connect(path)
        c = conn.cursor()
        c.execute('SELECT * from dbaseversion')
        v = c.fetchone()
        current = v[1]
        updates = {u.oldversion:u for u in dbupdates}
        while current != VERSION:
            update = updates[current]
            update.update(c)
            current = update.newversion
            c.execute('UPDATE dbaseversion SET version=%i'%current)
            conn.commit()
        conn.close()


###############################################################################
## Functions for managing the database
def openDb(url):
    ''' Create a new database from the URL
    '''
    print ('Using database', url)
    parts = urlparse(url)
    if parts.scheme == 'sqlite':
        path = parts.netloc or parts.path
        updateDb(path)
        db.bind(parts.scheme, path, create_db=True)
        db.generate_mapping(create_tables=True)
        with orm.db_session:
            if orm.count(d for d in DbaseVersion) == 0:
                v = DbaseVersion(version = VERSION)

    else:
        raise RuntimeError('Database %s not supported'%parts.scheme)


sessionScope = orm.db_session



###############################################################################
## Testing the basic workings of the database
def test():
    if os.path.exists('test.db'):
        os.remove('test.db')
    openDb('sqlite://test.db')
    with sessionScope():
        version = DbaseVersion.get()
        assert version.version == VERSION

        u = User()
    print ('tests OK')

if __name__ == '__main__':
    test()
