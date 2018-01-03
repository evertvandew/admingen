import cherrypy
import jwt
import time
import datetime
import base64
import logging
import json
import re
import bcrypt
from .db_api import sessionScope, commit, getHmiDetails
from pony.orm.core import EntityMeta

UNAME_FIELD_NAME = '__login_name__'
PWD_FIELD_NAME = '__login_password__'

# TODO: port to the Quart framework. https://gitlab.com/pgjones/quart
# TODO: make forms so that the contents are not re-evaluated each time?


def password2str(value):
    salt = bcrypt.gensalt()
    hash = bcrypt.hashpw(value, salt)
    return hash

def checkpasswd(clear, hashed):
    return bcrypt.checkpw(clear, hashed)

def ispwencrypted(p):
    return bool(re.match(r'^\$2a\$\d\d\$', p))


def NotEmpty(name):
    def check(params):
        p = params[name]
        if not p:
            return '%s must be entered' % name

    return check


def IsSingleWord(name):
    def check(params):
        w = params[name]
        if len(w.split()) > 1:
            return '%s must be a single word' % w

    return check


def IsInteger(name, minval=None, maxval=None):
    def check(params):
        try:
            value = int(params[name])
            params[name] = value
            if minval is not None and value < minval:
                return name, 'Value must be greater than %i' % minval
            if maxval is not None and value > maxval:
                return name, 'Value must be smaller than %i' % maxval
        except ValueError:
            return name, 'value must be an integer'

    return check


def GreaterEqual(a, b):
    def check(params):
        if params[a] < params[b]:
            return '%s must be greator or equal to %s' % (a, b)

    return check


def checkIfServer(host):
    if len(host.split()) > 1:
        return 'A host name must not contain spaces'


def IsServer(a):
    def check(params):
        host = params[a]
        return checkIfServer(host)

    return check


def IsEmailaddress(a):
    def check(params):
        email = params[a]
        if not '@' in email:
            return 'An email address must contain "@"'
        host = email.split('@')[1]
        if not checkIfServer(host):
            return 'Not a legal host identification: %s' % host
        if len(email.split()) > 1:
            return 'An email address must not contain spaces'

    return check


def Verify(params, *rules):
    def check():
        errors = {}
        results = dict(params)
        for r in rules:
            name_err = r(results)
            if name_err:
                errors[name_err[0]] = name_err[1]
        return results, errors

    return check


def Link(target, label):
    return '<A HREF=%s>%s</A>' % (target, label)


def joinElements(*args):
    return '\n'.join([a() if callable(a) else a for a in args])


def Container(tag, *children, **kwargs):
    if 'klasse' in kwargs:
        kwargs['class'] = kwargs['klasse']
        del kwargs['klasse']
    contents = joinElements(*children)
    options = ' '.join('%s="%s"' % o for o in kwargs.items())
    return '<%s %s>%s</%s>' % (tag, options, contents, tag)


def Div(*children, **kwargs):
    return Container('div', *children, **kwargs)


def Page(*args, refresh=None):
    body = joinElements(*args)
    headers = []
    if refresh:
        headers.append('<META HTTP-EQUIV="refresh" CONTENT="%s">' % refresh)
    return '''<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta http-equiv="X-UA-Compatible" content="IE=edge" />
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />
                <title>Overzichtgenerator</title>
            %(header)s
            <link rel="stylesheet" type="text/css" href="/static/css/bootstrap.min.css" />
            <link rel="stylesheet" type="text/css" href="/static/css/font-awesome.min.css" />
            <link rel="stylesheet" type="text/css" href="/static/css/custom-theme/jquery-ui-1.10.0.custom.css" />
            <link rel="stylesheet" type="text/css" href="/static/css/style.css" />

        </head>
        <body style="margin-top:0px">
        %(body)s
        </body>
        </html>
        ''' % {'body': body,
               'header': '\n'.join(headers)}


def Title(text):
    return '<H1 style="margin-top:0px">%s</H1>' % text


def ButtonBar(*args):
    buttons = ' '.join([b if isinstance(b, str) else b() for b in args])
    return '<div>%s</div>' % buttons


def Button(caption, target='"#"', btn_type='primary', **kwargs):
    args = ' '.join('%s="%s"' % o for o in kwargs.items())

    def get():
        btn_type_ = 'btn-%s' % btn_type if isinstance(btn_type, str) else ' '.join(
            ['btn-%s' % t for t in btn_type])
        return '<A HREF=%s class="btn %s" %s>%s</A>' % (target, btn_type_, args, caption)

    return get


def SimpleForm(*args, validator=None, defaults={}, success=None, action='POST',
               submit='Opslaan', enctype="multipart/form-data", readonly=False, cancel=None):
    # Handle the POST
    print('FORM GOT A REQUEST', cherrypy.request.method)
    errors = {}
    if cherrypy.request.method == 'POST':
        # Call the global validator
        if validator:
            values, errors = validator()
        else:
            values, errors = defaults, {}

        # Then call the validators linked to the individual inputs
        for a in args:
            if hasattr(a, 'validator'):
                values, errors = a.validator(values, errors)

        if not errors:
            # Call the success handler for each element
            for a in args:
                if hasattr(a, 'success'):
                    a.success(values)
            result = success(**values)
            if result:
                return result
        defaults.update(values)

    path = cherrypy.request.path_info

    # Determine which buttons to show
    if not success:
        btn = ''
    else:
        btns = ['<button class="btn btn-primary" type="submit" value="Submit">%s</button>' % submit]
        if cancel:
            btns.insert(0, Button('Cancel', target=cancel))
        btn = ButtonBar(*btns)

    # Generate the actual HTML for the form
    base = '''
      <div class="container">
        <div class="row">
          <div class="col col-md-12">
            <form action="%(action)s" method="post" enctype="%(enctype)s" class="form-horizontal">
                %(rows)s
                <div class="col col-md-9 col-md-offset-3">
                    %(btn)s
                </div>
            </form>
          </div>
        </div>
      </div>
    '''
    row_base = '''
        <div class="form-group">
            <label class="col col-md-3 control-label">%(label)s</label>
            <div class="col col-md-9">%(input)s</div>
        </div>
    '''
    row_base_no_label = '''
        <div class="col col-md-9 col-md-offset-3">%(input)s</div>
    '''
    rows = []
    for a in args:
        if callable(a):
            input = a(defaults, errors, readonly)
        else:
            input = a
        if 'label' in input:
            row = row_base
        else:
            row = row_base_no_label
        print(input)
        row = row % input
        rows.append(row)
    return base % {'rows': '\n'.join(rows), 'action': path,
                   'enctype': enctype, 'btn': btn}


def Hidden(name):
    def gen(defaults, errors, readonly):
        html = '<input type="hidden" name="%(name)s" value="%(value)s" />'
        return {'input': html % {'name': name, 'value': defaults.get(name, None)}}

    return gen


def FileUpload(name, text=None):
    text = text or name
    return {'label': text,
            'input': '<input type="file" name="%s" />' % name}


def form_input(name, text, input_type, tmpl=None):
    base = tmpl or '<input type="%(input_type)s" class="form-control" name="%(name)s" %(options)s value="%(default)s"/>'
    text = text or name

    def gen(defaults, errors, readonly):
        nonlocal base
        default = defaults.get(name, '')
        error = errors.get(name, '')
        options = []
        if readonly:
            options.append('readonly')
        if error:
            base += '<div class="errmsg">%(error)s</div>'
        result = base % {'input_type': input_type, 'name': name, 'error': error, 'default': default,
                         'options': ' '.join(options)}
        return {'label': text, 'input': result}

    return gen


def Integer(name, text=None):
    return form_input(name, text, 'number')


def String(name, text=None):
    return form_input(name, text, 'text')


def Text(name, text=None):
    return form_input(name, text, '',
                      '<textarea name="%(name)s" %(options)s >%(default)s</textarea>')


def Tickbox(name, text=None):
    base = '<input type="checkbox" name="%s" value="True" %s>'
    text = text or name

    def onSuccess(values):
        values[name] = name in values

    def gen(defaults, errors, readonly):
        nonlocal base
        default = defaults.get(name, False)
        options = []
        if readonly:
            options.append('disabled')
        if default:
            options.append('checked')
        result = base % (name, ' '.join(options))
        return {'label': text, 'input': result}

    gen.success = onSuccess
    return gen


Server = Email = String

def EnterPassword(name, text=None):
    return form_input(name, text, '')


def SetPassword(name, text=None):
    shadow_name = name + '_shadow'
    p1 = form_input(name, text, 'password')

    def set_default(defaults, errors, readonly):
        defaults[name] = ''
        return p1(defaults, errors, readonly)

    p2 = form_input(shadow_name, 'retype ' + text, 'password')

    def validator(values, errors):
        v1 = values[name]
        v2 = values[shadow_name]
        if v1 != v2:
            errors[name] = 'Both passwords must be the same!'
        if not v1:
            # The password is not being set: clear it.
            del values[name]
            del values[shadow_name]
        else:
            values[name] = password2str(v1)
            del values[shadow_name]
        return values, errors

    set_default.validator = validator
    return set_default, p2


def Selection(name, options, text=None):
    text = text or name

    def gen(defaults, errors, readonly):
        final_options = []
        index = None
        optionlist = options() if callable(options) else options

        if readonly:
            value = defaults.get(name, '')
            return {'label': text,
                    'input': '<input class="form-control" readonly value="%s"/>' % value}

        for i, o in enumerate(optionlist):
            if type(o) in [list, tuple]:
                value = (o[0], o[1])
            else:
                value = (o, o)
            final_options.append(value)
            if defaults.get(name, '') and value[1] == defaults[name]:
                index = i

        option_tags = ['<option value="%s">%s</option>' % o for o in final_options]
        if index:
            option_tags[i] = '<option selected="selected" value="%s">%s</option>' % final_options[i]
        args = 'name="%s"' % name
        if readonly:
            args += ' readonly'
        return {'label': text, 'input': '<select %s>' % args + '\n'.join(option_tags) + '</select>'}

    return gen


def DownloadLink(name, path):
    return '<A HREF="%s" target="_blank">%s</A>' % (path, name)


def PaginatedTable(line, data, header=None, row_select_url=None):
    ''' data: a generator that returns datasets, or some other iterable'''

    def get():
        head = ''
        if header:
            head = '<thead><tr>%s</tr></thead>' % '\n'.join('<th>%s</th>' % h for h in header)
        parts = []
        for d in data:
            l = line(d)
            p = '\n'.join(['<td>%s</td>' % c for c in l])
            oc = ''
            if row_select_url:
                su = row_select_url(d)
                oc = '''onclick="javascript:location.href='%s'"''' % su
            parts.append('<tr %s>%s</tr>' % (oc, p))
        b = '\n'.join(parts)
        return '<table class="table table-hover table-bordered">%s%s</table>' % (head, b)

    return get


def debug_source(data):
    def get():
        return data

    return get


def CheckOrCross(value):
    if value:
        return '<i class="fa fa-check text-success"></i>'
    else:
        return '<i class="fa fa-times text-danger"></i>'


def local_login(loginfunc):
    def decorator(func):
        def doIt(*args, **kwargs):
            if cherrypy.session.get('user_id', False):
                return func(*args, **kwargs)
            else:
                return loginfunc(**kwargs)

        return doIt

    return decorator


def ImgPathField(label, name):
    def success(values):
        ''' Called when the user has committed the values
        '''
        # Extract the image and store it in the externally available filesystem
        path = values[name].filename
        if not path:
            del values[name]
            return
        with open('public/static/' + path, 'wb') as out:
            while values[name].file:
                data = values[name].file.read(8192)
                if not data:
                    break
                out.write(data)
        # Let the database store the clean filename
        values[name] = path

    def gen(defaults, errors, readonly):
        clean_path = defaults[name]
        img = '<img src="/static/%s">' % clean_path
        if not readonly:
            img += '<input type="file" name="%s" />' % name
        return {'label': label, 'input': img}

    gen.success = success
    return gen


field_factory = {int: Integer,
                 str: String,
                 bool: Tickbox}

def AnnotationsForm(cls, validator=None, success=None, readonly=False):
    """ Generate a form from the annotations in a data (message) class """
    fields = [field_factory[t](n, n) for n, t in cls.__annotations__.items()]
    defaults = {n:getattr(cls, n) for n in cls.__annotations__ if hasattr(cls, n)}

    def gen():
        return SimpleForm(*fields,
                          validator=validator,
                          defaults=defaults,
                          success=success,
                          readonly=readonly)

    return gen


def dummyacm(func):
    return func


def ACM(permissions, login_func):
    """ Return a decorator useful for controlling access.
    """

    def decorate(func):
        acm = permissions.get(func.__name__, False)

        def doit(*args, **kwargs):
            if not cherrypy.session.get('user_id', False):
                result = login_func(**kwargs)
                if not cherrypy.session.get('user_id', False):
                    # The user is NOT logged in.
                    return result
                # The user logged-in, we need to move to a fresh 'GET' request
                cherrypy.request.method = 'GET'
                kwargs = eval(kwargs['org_arg'])  # FIXME: I am dangerous...
            role = cherrypy.session['role']
            if not acm or role in acm:
                return func(*args, **kwargs)
            raise cherrypy.HTTPError(403, 'Action not allowed')

        return doit

    return decorate


def generateFields(table, hidden=None):
    hidden = hidden or []
    for name, details in table['columns'].items():
        if type(a).__name__ == 'PrimaryKey' or a.column in hidden:
            yield Hidden(a.column)
        else:
            if a.type.__name__ == 'ImagePath':
                yield ImgPathField(name, name)
            elif details.options:
                yield Selection(name, details.options(), name)
            elif details.related_columns is not None:
                def makeGetter():
                    def options_getter():
                        with sessionScope:
                            cols = details.related_columns
                            result = [o for o in details.type.select()]
                            result = [(o._vals_[cols[0]], o._vals_[cols[1]]) for o in result]
                            if not result and details.is_required:
                                raise cherrypy.HTTPError(424,
                                                         "Please define an %s first" % details.type.__name__)
                            return result

                    return options_getter

                yield Selection(name, makeGetter(), name)
            elif details.type.__name__ == 'LongStr':
                yield Text(a.column, a.column)
            elif details.type.__name__ == 'Password':
                # Passwords are edited in duplicates
                elements = SetPassword(name, name)
                yield elements[0]
                yield elements[1]
            elif a.py_type == bool:
                yield Tickbox(name, name)
            else:
                yield String(name, name)


def generateCrud(table, Page=Page, hidden=None, acm=dummyacm, index_show=None):
    if isinstance(table, EntityMeta):
        # We have a database table definition: extract the necessary info
        table = getHmiDetails(table)

    tablename = table['name']
    columns = list(generateFields(table, hidden))
    column_names = table['columns'].keys()
    index_show = index_show or column_names

    class Crud:
        @cherrypy.expose
        @acm
        def index(self, **kwargs):
            def row_data(data):
                d = [getattr(data, k) for k in column_names if k in index_show]
                return d

            def row_select_url(data):
                return 'view?id=%s' % data.id

            with sessionScope:
                return Page(Title('%s overzicht' % tablename),
                            PaginatedTable(row_data, table.select(), row_select_url=row_select_url),
                            Button('Toevoegen <i class="fa fa-plus"></i>', target='add'))

        @cherrypy.expose
        @acm
        def view(self, id, **kwargs):
            with sessionScope:
                details = {k: getattr(table[id], k) for k in column_names}
            return Page(Title('%s details' % tablename),
                        SimpleForm(*columns,
                                   defaults=details,
                                   readonly=True),
                        ButtonBar(
                            Button('Verwijderen <i class="fa fa-times"></i>', btn_type=['danger'],
                                   target='delete?id=%s' % id),
                            Button('Aanpassen <i class="fa fa-pencil"></i>',
                                   target='edit?id=%s' % id),
                            Button('Sluiten', target='index')
                            ))

        @cherrypy.expose
        @acm
        def edit(self, **kwargs):
            id = kwargs['id']
            with sessionScope:
                details = table[id]

                def check():
                    return kwargs, {}

                def success(**kwargs):
                    for k, v in kwargs.items():
                        if getattr(details, k) != v:
                            setattr(details, k, v)
                    commit()
                    raise cherrypy.HTTPRedirect('view?id=%s' % kwargs['id'])

                return Page(Title('%s aanpassen' % tablename),
                            SimpleForm(*columns,
                                       defaults={k: getattr(table[id], k) for k in column_names},
                                       validator=check,
                                       success=success,
                                       cancel='view?id=%s' % id))

        @cherrypy.expose
        @acm
        def add(self, **kwargs):
            def success(**details):
                # Ensure there is no id
                if 'id' in details:
                    del details['id']
                with sessionScope:
                    print('Adding', details)
                    table(**details)
                return 'Success!'

            return Page(Title('%s toevoegen' % tablename),
                        SimpleForm(*columns,
                                   defaults={},
                                   validator=lambda: (kwargs, {}),
                                   success=success))

        @cherrypy.expose
        @acm
        def delete(self, **kwargs):
            id = kwargs['id']
            with sessionScope:
                def delete(**_):
                    table[id].delete()
                    commit()
                    raise cherrypy.HTTPRedirect('index')

                return Page(Title('Weet u zeker dat u %s wilt verwijderen?' % tablename),
                            SimpleForm(*columns,
                                       defaults={k: getattr(table[id], k) for k in column_names},
                                       readonly=True,
                                       submit='Verwijderen <i class="fa fa-times"></i>',
                                       success=delete,
                                       cancel='view?id=%s' % id))

    return Crud()


def simpleCrudServer(tables, page):
    class Server: pass

    for name, table in tables.items():
        setattr(Server, name, generateCrud(table))

    return Server


def runServer(server, config):
    cherrypy.config.update(config)

    # cherrypy.log.access_log.propagate = False
    logging.getLogger('cherrypy_error').setLevel(logging.ERROR)

    cherrypy.quickstart(server(), '/')

