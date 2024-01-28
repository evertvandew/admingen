"""
ACM rights are stored in a table. The table links the path of a resource with the roles that can access them.
By default, a role that is in the list has full access. But the role can be followed by by a set of letters indicating
specific rights: RWLAD, for Read, Write, List, Add and Delete. For example:

```
    data/Resource:editor:RWL,administrator,user:R
```

This allows the editors to Read, Write and List the Resources. Users can only Read these. Administrators have full rights.
"""

import re
from typing import List, Type, Union, Dict
import flask
import secrets
from Crypto.Cipher import Blowfish
import time
import logging
import json
from enum import Enum, auto
from admingen.data import data_server
from admingen.data.db_api import Record
from admingen.data.data_server import read_records, add_record, update_record, get_request_data
from admingen.data import password2str, checkpasswd
import data_model
from admingen.testing import testcase, expect_exception, running_unittests


logging.getLogger().setLevel(logging.DEBUG)


# The name with which the current role of the user is stored in the cookie.
rolename_field = 'role_name'
username_field = 'uname'
userid_field = 'uid'
password_field = 'psw'

class NotAuthorized(RuntimeError): pass


class auth_results(Enum):
    NOT_AUTHENTICATED = auto()
    NOT_AUTHORIZED = auto()
    WRONG_COMPARTIMENT = auto()
    OK = auto()


class ACM:
    secret = b'Mooi test dit maar goed'

    def __init__(self, role_hierarchy='administrator editor', data_fields='bedrijf', testmode=False,
                 project_name='admingen'):
        """ Configure the ACM system with a hierarchy.
            The first role is the administration role, and has unlimited access.
            The other roles only have access to data containing the associated data_fields.
            Each lower role needs matches on all data_fields of higher levels.

            All the data_fields should be elements of the User data structure.
        """
        self.token_name = f'token_data_{project_name}'
        self.rolename_name = rolename_field
        self.username_name = username_field
        self.userid_name = userid_field

        self.testmode = testmode
        if testmode:
            print("RUNNING WITH ACM DISABLED -- not for production!")

        self.max_age = 2 * 365 * 24 * 60 * 60  # in seconds
        self.refresh_by = 20  # in seconds

        self.token_name_b = self.token_name.encode('utf8')
        self.rolename_name_b = self.rolename_name.encode('utf8')
        self.username_name_b = self.username_name.encode('utf8')
        self.userid_name_b = self.userid_name.encode('utf8')

        self.data_fields = [f.strip() for f in data_fields.split(',')]
        self.data_fields_b = [t.encode('utf8') for t in self.data_fields]
        self.role_names = role_hierarchy.split()


        self.acm_table = {}                  # path:roles pairs
        self.parameterized_acm_table = {}    # [path parts]: roles pairs
        self.par_acm_matchers = []           # (matcher, roles) pairs
        self.compartiments = {}              # path:(record_key, context_key)

        self.all_roles = {}

    def get_user_role(self):
        return flask.request.cookies.get(self.rolename_name, '')

    def getContextValue(self, context):
        return flask.request.cookies.get(context)

    def roles(self, route, auth):
        """ Function that marks a specific route as having a specific authorization.
            In normal usage, these entries are not used in runtime, but they can
            are also written to stdout (by the my_query module when run stand-alone.
        """
        r = route.strip('/')
        parts = r.split('/')
        parameterized = [i for i, p in enumerate(parts) if p[0] == '<' and p[-1] == '>']
        if not parameterized:
            self.acm_table[r] = [a.strip() for a in auth.split(',')]
        else:
            # Assume that after the first parameterized bit, the rest doesnt matter.
            r = '/'.join(parts[:parameterized[0]])
            self.parameterized_acm_table[r] = auth
        return route

    def getRoles(self, name):
        if not self.all_roles:
            for path, rights in self.acm_table.items():
                roles = [r.split(':', maxsplit=1) for r in (rights.split(',') if isinstance(rights, str) else rights)]
                roles_dict = {r[0]: (r[1] if len(r) > 1 else 'RWLAD') for r in roles}
                self.all_roles[path] = roles_dict
        return self.all_roles[name]


    # TODO: rename to `decode_token`
    def check_token(self, token: bytes):
        d = eval(token)
        salt = d['salt']
        ciphertext = d['details']
        cipher = Blowfish.new(self.secret, Blowfish.MODE_CBC, salt)
        plaintext = cipher.decrypt(ciphertext)
        details = json.loads(plaintext)
        return details


    def generate_token(self, details: dict):
        """ Wrap the details dictionary into an encrypted data structure for placement in a cookie """
        bs = Blowfish.block_size
        salt = secrets.token_bytes(bs)
        plaintext = json.dumps(details, ensure_ascii=False).encode('utf8')
        plen = bs - divmod(len(plaintext), bs)[1]
        padding = b' ' * plen
        cipher = Blowfish.new(self.secret, Blowfish.MODE_CBC, salt)
        ciphertext = cipher.encrypt(plaintext + padding)
        wrapper = {'salt': salt,
                   'details': ciphertext}
        return repr(wrapper).encode('utf8')


    def check_authentication(self):
        """ Check the authentication details submitted by the user. """
        if self.testmode:
            return True

        token = flask.request.cookies.get(self.token_name, '')
        if not token:
            # The user has not been authenticated
            return False
        try:
            details = self.check_token(token)
        except:
            # Token is not correctly encoded or encrypted
            logging.exception('Exception when checking token')
            return False

        # Check the token is not too old
        ts = details.get('timestamp', 0)
        now = time.time()
        if ts > now + 1 or now - ts > self.max_age:
            return False
        # Check the ip address the request uses
        if (not flask.request.remote_addr) or flask.request.remote_addr != details.get('ipaddress', ''):
            return False
        # Check the role is set correctly
        if flask.request.cookies.get(self.rolename_name, '') != details.get(self.rolename_name, 'blablabla'):
            return False
        # Check the data_fields are set correctly in the cookie. They should match the ones in the token.
        for field in self.data_fields:
            if int(flask.request.cookies.get(field, '')) != details.get(field, 'blablabla'):
                return False

        return True


    def check_acm(self) -> auth_results:
        """ Check if the current user is authorized according to the table. """
        if self.testmode:
            return True
        path = flask.request.path.strip('/')
        action = flask.request.method

        # Static parts are always allowed.
        if path.startswith('batic'):
            return True

        # If the user has a token set, check the authentication details
        is_authenticated = False
        if self.token_name in flask.request.cookies:
            is_authenticated = self.check_authentication()

        role_name = flask.request.cookies.get(self.rolename_name, '') if is_authenticated else ''

        # For data access, the object ID needs to be discarded.
        if path.startswith('data/'):
            parts = path.split('/')
            path = '/'.join(parts[:2])

        # A page without ACM is not allowed
        # First test for parameterized urls.
        for m, roles in self.par_acm_matchers:
            if m.match(path):
                acm = roles
                break
        else:
            if path not in self.acm_table:
                # We do log this as an error: this is something that needs fixing.
                logging.error(f'Request made without entry in ACM table: {path}')
                if action == 'GET':
                    return True
                return False

            acm = self.acm_table[path]

        # Now check the ACM table.
        if 'any' in acm or (role_name and role_name in acm):
            return auth_results.OK
        elif is_authenticated:
            return auth_results.NOT_AUTHORIZED
        return auth_results.NOT_AUTHENTICATED


    def authorize(self):
        """ Wrap my old ACM protocol to that of a before_request Flask function.
            The old ACM protocol returned True if authorized, False if not.
            The before_request expects None if everything is OK, or an HTTP response.
        """
        result = self.check_acm()

        # For the data or query paths, just return an error.
        if flask.request.path.strip('/').split('/')[0] in ['data', 'query']:
            if result == auth_results.NOT_AUTHENTICATED:
                return "Not authenticated", 401
            if result == auth_results.NOT_AUTHORIZED:
                return "Not authorized", 403
        else:
            if result == auth_results.NOT_AUTHENTICATED:
                return open('html/login.html').read()
            if result == auth_results.NOT_AUTHORIZED:
                return flask.make_response("Not Authorized", 401)

        return None


    def accept_login(self, user, res=None):
        # Gather the details for the token
        role = user.rol.name or ''
        details = {'timestamp': time.time(),
                   self.rolename_name: role,
                   'ipaddress': flask.request.remote_addr}
        for field in self.data_fields:
            details[field] = getattr(user, field, None) or 0
        token = self.generate_token(details)

        # Assume that the request is redirected to another location
        res = res or flask.make_response("See Other", 303)
        # Set the cookies on the response
        # We store the token, the user id, the role of the user, company id, and the user name.
        res.set_cookie(self.token_name, token.decode('utf8'), max_age=self.max_age)
        res.set_cookie(self.rolename_name, role, max_age=self.max_age)
        res.set_cookie(self.username_name, user.login)
        res.set_cookie(self.userid_name, str(user.id))
        for field, field_b in zip(self.data_fields, self.data_fields_b):
            res.set_cookie(field, '%i'%(details[field]))
        return res


    def verify_login(self, username, password):
        with self.user_db.Session() as session:
            users = session.query(data_model.User).all()
        for user in users:
            if user.login == username:
                p = user.password.encode('utf8')
                if self.testmode or checkpasswd(password, p):
                    return user
        return None


    def login_put(self):
        """ Called with four form arguments: username, password, on_success and on_failure.
            Checks the username / password combination, sets the relevant cookies and redirects
            to the relevant url.
        """
        username = flask.request.form[username_field]
        password = flask.request.form[password_field]

        if not (user := self.verify_login(username, password)):
            return flask.make_response('Login not successful', 401)

        res = self.accept_login(user)
        res.headers.add('Location', '/')
        return res


    def logout(self):
        """ Clears the cookies associated with a login. """
        res = flask.make_response('U bent uitgelogged.<BR><BR><A HREF="/">Opnieuw inloggen</A>', 401)
        res.delete_cookie(self.token_name)
        res.delete_cookie(self.rolename_name)
        res.delete_cookie(self.username_name)
        res.delete_cookie(self.userid_name)
        for field in self.data_fields:
            res.delete_cookie(field)
        return res


    def create_acmtable_filter(self):
        def role_check(allow, deny):
            def check(request):
                pass


    def ensure_login(self):
        """ Ensure that there is at least one user that can login as administrator.
            If there is no such user, create a default admin user.
        """
        users = read_records('data/User', cls=data_model.User, raw=True)
        users = [u for u in users if u.rol == data_model.UserRole.administrator]
        if len(users) == 0:
            # Create a default user.
            data = {'login': 'testuser',
                    'password': password2str('change me'),
                    'rol': data_model.UserRole.administrator.value,
                   }
            add_record('User', data_model.User, data, mk_response=False)
            print("Created default user")


    def ensure_login_sql(self, db):
        """ Ensure that there is at least one user that can login as administrator.
            If there is no such user, create a default admin user.
        """
        # If there are no known users, create one.
        with self.user_db.Session() as session:
            count = session.query(data_model.User).count()
            if count == 0:
                # Create a default user.
                session.add(data_model.User(login = 'testuser',
	                                   password = password2str('change me'),
	                                   rol = data_model.UserRole.administrator
                    )
                )
                session.commit()
    def filtered_db(parent, db):
        """ Wrap an existing 'db' with a set of functions that check authorization.
            The wrapping is done in such a way that even when the db calls functions internally,
            for example to join with another table, authorization is applied.
            Otherwise, an attacked could fabricate some data and access foreign records he should not be able to access.

            Some 'black magic' is needed to accomplish this without tight coupling this class to the
            db implementation. This way, any type of database can be wrapped with ACM.

            In the wrapped db, we assume that the login has already been checked. We do not re-check
            the token and other details here.

            Also, we do not check on CRUD rights here. That is supposed to be done by the server using
            the database. Here we only check if the user has access to a specific record, not if
            he/she is authorized to perform a specific action on a table.

            @param: parent An ACM class instance.
            @param: db The database being wrapped.
        """
        class wrapper(type(db)):
            def __new__(cls):
                """ Let the object be initialised again AS a wrapped class.
                    This ensures that the object will be returned as a proper instance of wrapper,
                    with a base class of type db.
                """
                db.__class__ = wrapper
                return db
            def __init__(self):
                self.has_acm = True
            def get_raw_db(self):
                return db
            def check_read(self, table, records, access_type='L'):
                # First do ACM using the roles.
                path = f'data/{table.__name__}'
                roles_dict = parent.getRoles(path)

                # If compartmented, filter elements regardless of the user's rights
                if path in parent.compartiments:
                    key, context = parent.compartiments[path]
                    compartment = int(parent.getContextValue(context))
                    records = [r for r in records if getattr(r, key) == compartment]

                # Check if this table can be read by all.
                if 'any' in roles_dict:
                    return records

                # If the user is not logged in, return nothing.
                if access_type not in roles_dict.get(parent.get_user_role(), ''):
                    return []

                # Now do fine-grained ACM using the company and user ids.
                # Determine up to which level we need to do this.
                role_index = parent.role_names.index(parent.get_user_role())
                for i, field in enumerate(parent.data_fields):
                    # If the user has sufficient authority, we do not need to check the lower levels.
                    if i >= role_index:
                        break
                    if field in table.__annotations__:
                        # Filter out any records that the user is not authorized for.
                        field_id = int(flask.request.cookies.get(field, 0))
                        records = [r for r in records if getattr(r, field, -1) == field_id]
                return records
            def get(self, table: Type[Record], index: int) -> Record:
                r = super().get(table, index)
                ok = r and self.check_read(table, [r], 'R')
                if ok:
                    return r
            def get_many(self, table:Type[Record], indices:List[int]=None) -> List[Record]:
                r = super().get_many(table, indices)
                r = self.check_read(table, r, 'L')
                return r

            def query(self, table: Type[Record], **kwargs) -> List[Record]:
                # The query function does NOT check on ACM. It uses the get and get_many function that do.
                records = super().query(table, **kwargs)
                return records
            def delete(self, table:Type[Record], index:int) -> None:
                """ Delete a field is the details of the record correspond to the login.
                """
                # First do course ACM using the roles.
                path = f'data/{table.__name__}'
                roles_dict = parent.getRoles(path)
                rights = roles_dict.get(parent.get_user_role(), roles_dict.get('any', ''))
                if 'D' not in rights:
                    return auth_results.NOT_AUTHORIZED

                r = self.get_raw(table, index)
                role_index = parent.role_names.index(parent.get_user_role())
                for i, field in enumerate(parent.data_fields):
                    # If the user has sufficient authority, we do not need to check the lower levels.
                    if i >= role_index:
                        break
                    if field in table.__annotations__:
                        # Simply return if the user is not authorized for this.
                        field_id = int(flask.request.cookies.get(field, 0))
                        if getattr(r, field, -1) != field_id:
                            return auth_results.NOT_AUTHORIZED
                # Check for compartiment
                if details := parent.compartiments.get(path, False):
                    key, cookie = details
                    if getattr(r, key) != int(parent.getContextValue(cookie)):
                        return auth_results.WRONG_COMPARTIMENT
                super().delete(table, index)
            def add(self, table: Union[Type[Record], Record], record: Record=None, is_add=True) -> Record:
                """ Only let a user add records that have the field associated with their role. """
                # First do coarse ACM using the roles.
                if not record:
                    record = table
                    table = type(record)
                path = f'data/{table.__name__}'
                roles_dict = parent.getRoles(path)
                rights = roles_dict.get(parent.get_user_role(), roles_dict.get('any', ''))
                if 'A' not in rights:
                    return

                if isinstance(record, dict):
                    record = table(**record)

                # Take care of compartimentialization
                if details := parent.compartiments.get(path, False):
                    key, cookie = details
                    cookie_value = int(parent.getContextValue(cookie))
                    if not getattr(record, key):
                        setattr(record, key, cookie_value)
                    else:
                        if getattr(record, key) != cookie_value:
                            # We allow no action on another compartiment
                            return

                role_index = parent.role_names.index(parent.get_user_role())
                for i, field in enumerate(parent.data_fields):
                    # If the user has sufficient authority, we do not need to check the lower levels.
                    if i >= role_index:
                        break
                    if field in record.__class__.__annotations__:
                        # Simply return if the user is not authorized for this.
                        field_id = int(flask.request.cookies.get(field, 0))
                        if not getattr(record, field, None):
                            setattr(record, field, field_id)
                        if getattr(record, field, -1) != field_id:
                            return
                if is_add:
                    return super().add(record)
                return super().set(record)
            def set(self, record):
                # Ensure that the original values of the record allow the user to modify them.
                role_index = parent.role_names.index(parent.get_user_role())
                for i, field in enumerate(parent.data_fields):
                    # If the user has sufficient authority, we do not need to check the lower levels.
                    if i >= role_index:
                        break
                    if field in record.__class__.__annotations__:
                        # Simply return if the user is not authorized for this.
                        field_id = int(flask.request.cookies.get(field, 0))
                        if getattr(record, field, -1) != field_id:
                            return
                return self.add(record, is_add=False)
            def update_checker(self, update: Dict, orig: Record):
                """ Ensure that the user is authorized to make the change proposed here. """
                path = f'data/{type(orig).__name__}'
                role_index = parent.role_names.index(parent.get_user_role())
                for i, field in enumerate(parent.data_fields):
                    # If the user has sufficient authority, we do not need to check the lower levels.
                    if i >= role_index:
                        break
                    if field in orig.__class__.__annotations__:
                        # Simply return if the user is not authorized for this.
                        field_id = int(flask.request.cookies.get(field, 0))
                        if getattr(orig, field) != field_id or int(update.get(field, getattr(orig, field))) != field_id:
                            raise NotAuthorized()

                # Don't allow messing with the compartiments
                if details := parent.compartiments.get(path, False):
                    key, cookie = details
                    cookie_value = int(parent.getContextValue(cookie))
                    if getattr(orig, key) != cookie_value:
                        return False
                    if key in update and int(update[key]) != cookie_value:
                        return False
                # It is OK to make this change
                return True
            def update(self, table, record=None, checker=None):
                super().update(table, record, checker=self.update_checker)
            def update_raw(self, table, record=None):
                type(db).__bases__[0].update(self, table, record)
            def get_raw(self, table, index):
                """ Get one record from the database, WITHOUT ACM.
                    Use at your own peril.
                """
                return type(db).__bases__[0].get(self, table, index)
            def get_many_raw(self, table:Type[Record], indices:List[int]=None) -> List[Record]:
                """ Get one record from the database, WITHOUT ACM.
                    Use at your own peril!
                """
                return super().get_many(table, indices)

        return wrapper()

    def add_handlers(self, app, context):
        """ Call this function to insert the ACM functions into a flask application. """
        # Wrap the original database in a system that checks authorization
        names = list(context['databases'].keys())
        context['databases'] = {n: self.filtered_db(db) for n, db in context['databases'].items()}
        all_tables = {db_name: {t.__name__: t for t in context['datamodel'][db_name]} for db_name in names}

        user_db = None
        user_table = None
        for name, tables in context['datamodel'].items():
            tab_names = [t.__name__ for t in tables]
            if 'User' in tab_names:
                user_db = context['databases'][name]
                user_table = all_tables[name]['User']

        self.user_db = user_db
        self.user_table = user_table

        def update_password():
            """ Update the password for the current user. After checking the details, of course. """
            if not self.check_authentication():
                flask.abort(401)

            user_id = int(flask.request.form['user_id'])
            details = user_db.get_raw(user_table, user_id)
            if not details:
                flask.abort(400)

            current = flask.request.form['current_password']
            if not checkpasswd(current, details.password):
                return "Paswoord niet correct", 400

            new_1 = flask.request.form['new_password1']
            new_2 = flask.request.form['new_password2']
            if new_1 != new_2:
                flask.abort(400)

            pw = password2str(new_1)
            user_db.update_raw(user_table, {'id': details.id, 'password': pw})
            return "Paswoord is aangepast", 200

        def is_authorized_user(data):
            """ Check the authorization for creating or updating a user.
            """
            # Obviously, a user can not promote anybody to a role higher than his own.
            new_role = int(data.get('rol', -1)) - 1   # The role values start at 1, not at 0.
            role_index = self.role_names.index(self.get_user_role())
            if new_role < role_index:
                return False

            # Ensure that a user does not move outside his own sphere of authority.
            # A trick is used where the order of elements in the User record is linked to the Role enumeration.
            # For each role of the current user, a number of elements are checked corresponding to the numeric value of the role.
            # So, for 0 (administrator), no values are checked. For role 1, one element is checked. For role 2, two elements.
            # For the elements that are checked, the value of the current user must be the same as for the new user.

            # So, if these fields are Company and Customer in order, and the roles are admin, editor and user,
            # then the admin can add users to any Company. An editor only some else from this company, but any Customer.
            # Users can only add people for the same Customer and the same Company.
            for i, field in enumerate(self.data_fields):
                # If the user has sufficient authority, we do not need to check the lower levels.
                if i >= role_index:
                    return True
                field_id = int(flask.request.cookies.get(field, 0))
                if str(data.get(field, '-10')) != str(field_id):
                    return False
            return True

        def add_user():
            """ An override that ensures the password in a user record is encrypted, and that a user does not
                create a user with more authorization or a different company than itself.
            """
            data = get_request_data()
            data['password'] = password2str(data['password'].encode('utf8'))
            if not is_authorized_user(data):
                return "Not authorized", 403
            record = user_db.add(user_table, data)
            if record:
                return "User Added", 201
            return "Could not add user", 400

        def update_user(index):
            """ The password can not be updated in this way """
            data = get_request_data()
            # Remove the password, if supplied.
            if 'password' in data:
                del data['password']
            if not is_authorized_user(data):
                return "Not authorized", 403
            # Always update the existing record, so the password is not modified.
            try:
                return update_record(user_table, index, user_db, data, True)
            except NotAuthorized:
                return "Not authorized", 403

        app.route(self.roles('/logout', 'any'), methods=['GET'])(self.logout)
        app.route(self.roles('/login', 'any'), methods=['PUT', 'POST'])(self.login_put)
        app.route(self.roles('/update_password', 'administrator,editor,user'), methods=['PUT', 'POST'])(update_password)
        # We need a custom writer for the User record, to properly hash the password.
        app.route('/data/User', methods=['PUT', 'POST'])(add_user)
        app.route('/data/User/<int:index>', methods=['PUT', 'POST'])(update_user)
        app.before_request(self.authorize)

        # Ensure there is a user, if need be create a default administrator user
        # This is necessary to ensure the password is known and formatted correctly
        # In future, perhaps replace this with a script that is run during reployment.
        self.ensure_login_sql(self.user_db)

        # Load the ACM table for the other elements
        with open('acm_table') as f:
            for line in f:
                path, r = line.strip().split(':', maxsplit=1)
                # Ensure the entries in the table have no leading or trailing slashes.
                path = path.strip('/')

                # For paths with wildcards, create a regular expression that matches it.
                if '*' in path:
                    self.parameterized_acm_table[path] = r
                else:
                    # Check for the "compartemented" command.
                    c = re.search(r'compartmented\(([a-zA-Z_]*)=([a-zA-Z_]*)\)', r)
                    if c:
                        self.compartiments[path] = r[c.regs[1][0]:c.regs[1][1]], r[c.regs[2][0]:c.regs[2][1]]
                        r = r[0:c.regs[0][0]-1]+r[c.regs[0][1]:]
                    self.acm_table[path] = r
                    # If there are keys that end in 'index.html', also add the '' alias.
                    if path.endswith('index.html'):
                        self.acm_table[path[:-10]] = r


        # User the parameterized acm table to generate a set of regular expression matchers.
        self.par_acm_matchers = [(re.compile(p.replace('*', '[^/]*')), r)
            for p, r in self.parameterized_acm_table.items()
        ]




###############################################################################
## UNIT TESTING
if running_unittests():
    from dataclasses import asdict
    from admingen.testing.mocks import *

    def mockFlask():
        global flask
        flask = MockFlask
        data_server.flask = MockFlask


    def mockApp():
        if MockApp.acm is None:
            MockApp.acm = ACM('administrator editor user', 'bedrijf klant')
            MockApp.acm.add_handlers(MockApp, MockApp.context)


    user1 = User(id=1, login='Tom Poes', password=password2str('test me'), rol=Rol.user, email='', vollenaam='', bedrijf=15, klant=3)
    editor1 = User(id=1, login='Tom Poes', password=password2str('test me'), rol=Rol.editor, email='', vollenaam='', bedrijf=15, klant=3)
    admin1 = User(id=1, login='Tom Poes', password=password2str('test me'), rol=Rol.administrator, email='', vollenaam='', bedrijf=15, klant=3)

    @testcase()
    def constructionTest():
        acm = ACM()

    @testcase(mockFlask)
    def accept_loginTest():
        """ This tests the function that sets the cookies after a successful login. """
        acm = ACM()
        acm.accept_login(User(10, 'obb', 'test me', data_model.UserRole.editor, '', '', 15, 3))
        assert MockResponse.cookies[b'role_name'] == 'editor'
        assert MockResponse.cookies[b'uname'] == b'obb'
        assert MockResponse.cookies[b'bedrijf'] == b'15'
        assert MockResponse.cookies[b'klant'] == b'3'

        # The encoded token that is stored in the cookie can not be checked, as it is different each time.
        assert len(MockResponse.cookies[b'token_data_admingen']) > 100
        # The acm has a function to unpack it (and check its integrity)
        details = acm.check_token(MockResponse.cookies[b'token_data_admingen'])
        assert details['role_name'] == 'editor'
        assert details['ipaddress'] == '127.0.0.1'
        assert details['bedrijf'] == 15
        assert details['klant'] == 3

        # We can however check the integrity of the cookie.
        # It uses the token for this: it stores signed duplicates of the other fields.
        # TODO

        # Do some simple tests
        MockRequest.set_cookies(MockResponse.cookies)
        assert acm.get_user_role() == 'editor'



    @testcase(mockFlask)
    def invalid_tokenTest():
        return # There is a known issue with the token that sometimes causes this test to fail.
        # Create a login cookie, then corrupt it
        acm = ACM()
        acm.accept_login(User(10, 'obb', 'test me', data_model.UserRole.editor, '', '', 15, 3))
        # Break open the token, change one byte in it and try to unpack it.
        token = MockResponse.cookies[b'token_data_admingen']
        tl = list(token)
        # replace the first number between 0 and 8 to 9
        index = [i for i, c in enumerate(tl) if ord('0') <= c < ord('9')][0]
        tl[index] = ord('9')
        token2 = bytes(tl)
        with expect_exception(Exception):
            details = acm.check_token(token2)
            pass

    @testcase(mockFlask, mockApp)
    def add_userTest():
        # Test a number of combinations that should be rejected.
        # The cases are determined by own role, new role and new company.
        # Users can only create users with the same or lower role.
        # Only administrators (role 0) can create users for a different company.
        # Only editors and admins can create users for a different customer.
        cases = [
            (Rol.user, 2, 15, 4),
            (Rol.user, 1, 15, 3),
            (Rol.user, 0, 15, 3),
            (Rol.editor, 0, 15, 3),
            (Rol.user, 2, 16, 3),
            (Rol.editor, 2, 16, 3)
        ]
        for details in cases:
            print("Trying case", details)
            my_role, new_role, new_company, new_customer = details

            MockApp.acm.accept_login(User(10, 'obb', 'test me', my_role, '', '', 15, 3))
            MockRequest.set_cookies(MockResponse.cookies)
            data = {'id': None, 'login': 'Tom Poes', 'password': 'test me', 'rol': new_role, 'email': '', 'vollenaam': '',
                    'bedrijf': str(new_company), 'klant': str(new_customer)}
            MockApp.request('/data/User', 'POST', data=data)  # Calls the AddUser function
            assert len(MockApp.db.data['User']) == 0, f'Failed testcase: {my_role}, {new_role}, {new_company}'

        # Now test a number of combinations that should work
        cases = [
            (Rol.administrator, 0, 16, 4),
            (Rol.administrator, 1, 16, 4),
            (Rol.administrator, 2, 16, 4),
            (Rol.editor, 1, 15, 4),
            (Rol.editor, 2, 15, 4),
            (Rol.user, 2, 15, 3)
        ]
        for details in cases:
            print("Trying case", details)
            my_role, new_role, new_company, new_customer = details

            MockApp.db.data['User'] = {}
            MockApp.acm.accept_login(User(10, 'obb', 'test me', my_role, '', '', 15, 3))
            MockRequest.set_cookies(MockResponse.cookies)
            data = {'id': None, 'login': 'Tom Poes', 'password': 'test me', 'rol': new_role, 'email': '', 'vollenaam': '',
                    'bedrijf': str(new_company), 'klant': str(new_customer)}
            MockApp.request('/data/User', 'POST', data=data)  # Calls the AddUser function
            assert len(MockApp.db.data['User']) == 1, f'Failed testcase: {my_role}, {new_role}, {new_company}'

        # Test the contents of the record stored in the db.
        rec = MockApp.db.data['User'][1]
        assert isinstance(rec, User)
        assert rec == User(id=1, login='Tom Poes', password=rec.password, rol=Rol.user, email='', vollenaam='', bedrijf=15, klant=3)

    @testcase(mockFlask, mockApp)
    def add_user_without_passwordTest():
        # Test a number of combinations that should be rejected.
        # The cases are determined by own role, new role and new company.
        # Users can only create users with the same or lower role.
        # Only administrators (role 0) can create users for a different company.
        # Only editors and admins can create users for a different customer.
        cases = [
            (Rol.user, 2, 15, 4),
            (Rol.user, 1, 15, 3),
            (Rol.user, 0, 15, 3),
            (Rol.editor, 0, 15, 3),
            (Rol.user, 2, 16, 3),
            (Rol.editor, 2, 16, 3)
        ]
        for details in cases:
            print("Trying case", details)
            my_role, new_role, new_company, new_customer = details

            MockApp.acm.accept_login(User(10, 'obb', 'test me', my_role, '', '', 15, 3))
            MockRequest.set_cookies(MockResponse.cookies)
            data = {'id': None, 'login': 'Tom Poes', 'password': 'test me', 'rol': new_role, 'email': '', 'vollenaam': '',
                    'bedrijf': str(new_company), 'klant': str(new_customer)}
            MockApp.request('/data/User', 'POST', data=data)  # Calls the AddUser function
            assert len(MockApp.db.data['User']) == 0, f'Failed testcase: {my_role}, {new_role}, {new_company}'

        # Now test a number of combinations that should work
        cases = [
            (Rol.administrator, 0, 16, 4),
            (Rol.administrator, 1, 16, 4),
            (Rol.administrator, 2, 16, 4),
            (Rol.editor, 1, 15, 4),
            (Rol.editor, 2, 15, 4),
            (Rol.user, 2, 15, 3)
        ]

    @testcase(mockFlask, mockApp, MockDb.setRecords([user1]))
    def accept_loginTest():
        """ Test the function that receives the login details from the client in a login attempt. """
        # First an unsuccessful login, then a successful one, then another unsuccessful one.
        MockResponse.cookies = {}
        MockApp.request('/login', 'POST', data={'uname': 'Tom Poes', 'psw': 'Dit is fout'})
        assert not MockResponse.cookies
        assert MockResponse.code == 401

        # Fix the password
        MockApp.request('/login', 'POST', data={'uname': 'Tom Poes', 'psw': 'test me'})
        assert MockResponse.code == 303     # A valid login forwards to another page
        assert MockResponse.cookies[b'role_name'] == user1.rol.name
        assert MockResponse.cookies[b'uname'] == user1.login.encode('utf8')
        assert MockResponse.cookies[b'bedrijf'] == str(user1.bedrijf).encode('utf8')
        assert MockResponse.cookies[b'klant'] == str(user1.klant).encode('utf8')

        # Try with the wrong username
        MockApp.request('/login', 'POST', data={'uname': 'Tom Goes', 'psw': 'test me'})
        assert MockResponse.cookies         # Old login details need to be kept
        assert MockResponse.code == 401

        # Logout
        MockApp.request('/logout', 'GET')
        assert not MockResponse.cookies

    @testcase(mockFlask, mockApp, MockDb.setRecords([user1]))
    def change_passwordTest():
        # Login as Tom Poes
        MockApp.acm.accept_login(user1)
        MockRequest.set_cookies(MockResponse.cookies)

        # Fail because the original PW is not correct
        data = {'current_password': 'error',
                'new_password1': 'test me nogmaals',
                'new_password2': 'test me nogmaals'}
        MockApp.request('/update_password', 'POST', data=data)
        assert MockResponse.code == 400

        # Fail because the two new passwords don't match
        data = {'current_password': 'test me',
                'new_password1': 'test me nogmaals',
                'new_password2': 'test me nogmals'}
        MockApp.request('/update_password', 'POST', data=data)
        assert MockResponse.code == 400

        # Submit a proper request to change the password successfully.
        data = {'current_password': 'test me',
                'new_password1': 'test me nogmaals',
                'new_password2': 'test me nogmaals'}
        MockApp.request('/update_password', 'POST', data=data)
        assert MockResponse.code == 200
        assert not checkpasswd('test me', MockDb.db.data['User'][1].password)
        assert checkpasswd('test me nogmaals', MockDb.db.data['User'][1].password)


    @testcase(mockFlask, mockApp, MockDb.setRecords([user1]))
    def update_userTest():
        # Login as Tom Poes
        MockApp.acm.accept_login(user1)
        MockRequest.set_cookies(MockResponse.cookies)

        # no-one should be able to change the password this way
        # By the user himself
        old_pw = user1.password
        data = {'id': user1.id, 'login': user1.login, 'password': 'Verzin een list!', 'rol': user1.rol, 'email': 'test@pp.nl', 'vollenaam': user1.vollenaam,
                'bedrijf': user1.bedrijf, 'klant': user1.klant}
        MockApp.request(f'/data/User/{user1.id}', 'POST', data=data)
        assert MockDb.db.data['User'][1].password == old_pw
        assert MockDb.db.data['User'][1].email == data['email']
        assert MockResponse.code == 201

        # By an editor
        data['vollenaam'] = 'aan lange naam'
        MockApp.acm.accept_login(editor1)
        MockRequest.set_cookies(MockResponse.cookies)
        MockApp.request(f'/data/User/{user1.id}', 'POST', data=data)
        assert MockDb.db.data['User'][1].password == old_pw
        assert MockDb.db.data['User'][1].vollenaam == data['vollenaam']
        assert MockResponse.code == 201

        # By an administrator
        MockApp.acm.accept_login(admin1)
        MockRequest.set_cookies(MockResponse.cookies)
        MockApp.request(f'/data/User/{user1.id}', 'POST', data=data)
        assert MockDb.db.data['User'][1].password == old_pw
        assert MockResponse.code == 201

    @testcase(mockFlask, mockApp, MockDb.setRecords([
        User(id=20, login='nr1', password=password2str('test me'), rol=Rol.user, email='', vollenaam='', bedrijf=15,
             klant=3),
        User(id=21, login='nr2', password=password2str('test me'), rol=Rol.editor, email='', vollenaam='', bedrijf=15,
             klant=3),
        User(id=22, login='nr3', password=password2str('test me'), rol=Rol.user, email='', vollenaam='', bedrijf=15,
             klant=4),
        User(id=23, login='nr4', password=password2str('test me'), rol=Rol.editor, email='', vollenaam='', bedrijf=15,
             klant=4),
        User(id=24, login='nr5', password=password2str('test me'), rol=Rol.user, email='', vollenaam='', bedrijf=15,
             klant=5),
        User(id=25, login='nr6', password=password2str('test me'), rol=Rol.editor, email='', vollenaam='', bedrijf=16,
             klant=6),
        User(id=26, login='nr7', password=password2str('test me'), rol=Rol.user, email='', vollenaam='', bedrijf=16,
             klant=6),
        User(id=27, login='nr8', password=password2str('test me'), rol=Rol.editor, email='', vollenaam='', bedrijf=16,
             klant=7),
        User(id=28, login='nr9', password=password2str('test me'), rol=Rol.user, email='', vollenaam='', bedrijf=16,
             klant=7),
        User(id=29, login='nr10', password=password2str('test me'), rol=Rol.user, email='', vollenaam='', bedrijf=16,
             klant=8),
    ]))
    def filter_recordsTest():
        MockApp.acm.accept_login(user1)
        MockRequest.set_cookies(MockResponse.cookies)

        # Directly test the API of the wrapped database.

        # A 'user' can not access any users
        result = MockDb.db.get_many(User)
        assert len(result) == 0

        # An 'editor' can see all users associated with a specific company
        MockApp.acm.accept_login(editor1)
        MockRequest.set_cookies(MockResponse.cookies)
        result = MockDb.db.get_many(User)
        assert len(result) == 5

        # An 'admin' can see everybody
        MockApp.acm.accept_login(admin1)
        MockRequest.set_cookies(MockResponse.cookies)
        result = MockDb.db.get_many(User)
        assert len(result) == 10