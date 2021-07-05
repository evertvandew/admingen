"""

"""

import re
import flask
import secrets
from Crypto.Cipher import Blowfish
import time
import logging
import json
import enum
from admingen.data.data_server import read_records, add_record, update_record, get_request_data
from admingen.data import password2str, checkpasswd
import data_model


the_db = None


logging.getLogger().setLevel(logging.DEBUG)


# The name with which the current role of the user is stored in the cookie.
rolename_name = 'role_name'


class NotAuthorized(RuntimeError): pass


class auth_results(enum.Enum):
    NOT_AUTHENTICATED = 1
    NOT_AUTHORIZED = 2
    OK = 3


class ACM:
    secret = b'Mooi test dit maar goed'

    def __init__(self, role_hierarchy='administrator editor user', data_fields='bedrijf klant', testmode=False):
        """ Configure the ACM system with a hierarchy.
            The first role is the administration role, and has unlimited access.
            The other roles only have access to data containing the associated data_fields.
            Each lower role needs matches on all data_fields of higher levels.

            All the data_fields should be elements of the User data structure.
        """
        self.token_name = 'token_data'
        self.rolename_name = 'role_name'
        self.username_name = 'user_name'

        self.testmode = testmode
        if testmode:
            print("RUNNING WITH ACM DISABLED -- not for production!")

        self.max_age = 2 * 365 * 24 * 60 * 60  # in seconds
        self.refresh_by = 20  # in seconds

        self.token_name_b = self.token_name.encode('utf8')
        self.rolename_name_b = self.rolename_name.encode('utf8')
        self.username_name_b = self.username_name.encode('utf8')

        self.data_fields = data_fields.split()
        self.data_fields_b = [t.encode('utf8') for t in self.data_fields]
        self.role_names = role_hierarchy.split()


        self.acm_table = {}                  # path:roles pairs
        self.parameterized_acm_table = {}    # [path parts]: roles pairs
        self.par_acm_matchers = []           # (matcher, roles) pairs

    @staticmethod
    def get_user_role():
        return flask.request.cookies.get(rolename_name, '')

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


    def check_token(self, token: dict):
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
        if flask.request.cookies.get(rolename_name, '') != details.get(rolename_name, 'blablabla'):
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
                   rolename_name: role,
                   'ipaddress': flask.request.remote_addr}
        for field in self.data_fields:
            details[field] = getattr(user, field, None) or 0
        token = self.generate_token(details)

        # Assume that the request is redirected to another location
        res = res or flask.make_response("See Other", 303)
        # Set the cookies on the response
        # We store the token, the user id, the role of the user, company id, and the user name.
        res.set_cookie(self.token_name_b, token, max_age=self.max_age)
        res.set_cookie(self.rolename_name_b, role, max_age=self.max_age)
        res.set_cookie(self.username_name_b, user.login.encode('utf-8'))
        for field, field_b in zip(self.data_fields, self.data_fields_b):
            res.set_cookie(field_b, b'%i'%(details[field]))
        return res


    def verify_login(self, username, password):
        for user in read_records('data/User', cls=data_model.User, raw=True):
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
        username = flask.request.form['uname']
        password = flask.request.form['psw']

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
            data = {'login': 'evert',
                    'password': password2str('verander mij'),
                    'rol': data_model.UserRole.administrator.value,
                   }
            add_record('User', data_model.User, data, mk_response=False)
            print("Created default user")


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
            def check_read(self, table, records):
                # First do course ACM using the roles.
                roles = parent.acm_table.get(f'data/{table.__name__}', '').split(',')
                if 'any' in roles:
                    return records
                if parent.get_user_role() not in roles:
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
            def get(self, table, index):
                r = super().get(table, index)
                ok = r and self.check_read(table, [r])
                if ok:
                    return r
            def get_many(self, table, indices=None):
                r = super().get_many(table, indices)
                r = self.check_read(table, r)
                return r
            def query(self, table, **kwargs):
                # The query function does NOT check on ACM. It uses the get and get_many function that do.
                records = super().query(table, **kwargs)
                return records
            def delete(self, table, index):
                """ Delete a field is the details of the record correspond to the login.
                    Currently, the ACM table is not checked.
                """
                r = super().get(table, index)
                role_index = parent.roles.index(parent.get_user_role)
                for i, field in enumerate(parent.data_fields):
                    # If the user has sufficient authority, we do not need to check the lower levels.
                    if i >= role_index:
                        break
                    if field in table.__annotations__:
                        # Simply return if the user is not authorized for this.
                        field_id = int(flask.request.cookies.get(field, 0))
                        if getattr(r, field, -1) != field_id:
                            return
                super().delete(table, index)
            def add(self, record, is_add=True):
                """ Only let a user add records that have the field associated with their role. """
                role_index = parent.roles.index(parent.get_user_role)
                for i, field in enumerate(parent.data_fields):
                    # If the user has sufficient authority, we do not need to check the lower levels.
                    if i >= role_index:
                        break
                    if field in record.__class__.__annotations__:
                        # Simply return if the user is not authorized for this.
                        field_id = int(flask.request.cookies.get(field, 0))
                        if getattr(record, field, -1) != field_id:
                            return
                if is_add:
                    return super().add(record)
                return super().set(record)
            def set(self, record):
                # Ensure that the original values of the record allow the user to modify them.
                role_index = parent.roles.index(parent.get_user_role())
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
            def update_checker(self, update, orig):
                """ Ensure that the user is authorized to make the change proposed here. """
                role_index = parent.roles.index(parent.get_user_role())
                for i, field in enumerate(parent.data_fields):
                    # If the user has sufficient authority, we do not need to check the lower levels.
                    if i >= role_index:
                        break
                    if field in orig.__class__.__annotations__:
                        # Simply return if the user is not authorized for this.
                        field_id = int(flask.request.cookies.get(field, 0))
                        if getattr(orig, field) != field_id or int(update[field]) != field_id:
                            raise NotAuthorized()
                return True
            def update(self, table, record=None):
                super().update(table, record, checker=self.update_checker)
            def get_raw(self, table, index):
                """ Get one record from the database, WITHOUT ACM.
                    Use at your own peril.
                """
                return super().get(table, index)

        return wrapper()

    def add_handlers(self, app, context):
        """ Call this function to insert the ACM functions into a flask application. """
        # Wrap the original database in a system that checks authorization
        names = list(context['databases'].keys())
        for db_name in names:
            db = self.filtered_db(context['databases'][db_name])
            context['databases'][db_name] = db

        def update_password():
            """ Update the password for the current user. After checking the details, of course. """
            if not self.check_authentication():
                return "Not authenticated", 401

            user_id = int(flask.request.cookies.get(userid_name, ''))
            details : data_model.User = db.get_raw(data_model.User, user_id)
            if not details:
                return "User not found", 404

            current = flask.request.form['current_password']
            if not checkpasswd(current, details.password):
                return "Paswoord niet correct", 400

            new_1 = flask.request.form['new_password1']
            new_2 = flask.request.form['new_password2']
            if new_1 != new_2:
                return "Nieuwe paswoorden kloppen niet", 400

            pw = password2str(new_1)
            db.update(data_model.User, {'id': details.id, 'password': pw})
            return "Paswoord is aangepast", 200

        def is_authorized_user(self, data):
            """ Check the authorization for creating or updating a user.
            """
            # Obviously, a user can not promote anybody to a role higher than his own.
            new_role = int(data.get('rol', -1))
            role_index = self.role_names.index(self.get_user_role())
            new_index = self.role_names.index(new_role)
            if new_index < role_index:
                return False

            # Ensure that a user does not move outside his own sphere of authority.
            for i, field in enumerate(self.data_fields):
                # If the user has sufficient authority, we do not need to check the lower levels.
                if i >= role_index:
                    return True
                field_id = int(flask.request.cookies.get(field, 0))
                if data.get(field, '-10') != str(field_id):
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
            return add_record('User', data_model.User, data)

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
                return update_record(data_model.User, index, db, data, True)
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
        self.ensure_login()

        # Load the ACM table for the other elements
        with open('acm_table') as f:
            for line in f:
                path, r = line.strip().split(':')
                # Ensure the entries in the table have no leading or trailing slashes.
                path = path.strip('/')

                # For paths with wildcards, create a regular expression that matches it.
                if '*' in path:
                    self.parameterized_acm_table[path] = r
                else:
                    self.acm_table[path] = r
                    # If there are keys that end in 'index.html', also add the '' alias.
                    if path.endswith('index.html'):
                        self.acm_table[path[:-10]] = r


        # User the parameterized acm table to generate a set of regular expression matchers.
        self.par_acm_matchers = [(re.compile(p.replace('*', '[^/]*')), r)
            for p, r in self.parameterized_acm_table.items()
        ]
