from .http_framework import request_method, request_params, request_path, session_get, result_type
import admingen.htmltools.http_framework
import logging
import json
import re
import os.path
from contextlib import contextmanager
from urllib.parse import urlparse
from typing import Dict, Callable, Any, Iterable
import bcrypt



UNAME_FIELD_NAME = 'username'
PWD_FIELD_NAME = 'password'


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
            return '{} must be entered'.format(name)

    return check


def IsSingleWord(name):
    def check(params):
        w = params[name]
        if len(w.split()) > 1:
            return '{} must be a single word'.format(w)

    return check


def IsInteger(name, minval=None, maxval=None):
    def check(params):
        try:
            value = int(params[name])
            params[name] = value
            if minval is not None and value < minval:
                return name, 'Value must be greater than {}'.format(minval)
            if maxval is not None and value > maxval:
                return name, 'Value must be smaller than {}'.format(maxval)
        except ValueError:
            return name, 'value must be an integer'

    return check


def GreaterEqual(a, b):
    def check(params):
        if float(params[a]) < float(params[b]):
            return '{} must be greator or equal to {}'.format(a, b)

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
            return 'Not a legal host identification: {}'.format(host)
        if len(email.split()) > 1:
            return 'An email address must not contain spaces'

    return check


def IsUrl(a, host=True, scheme=True):
    """ if host and/or scheme is True, a host and/or scheme is required
    """

    def check(params):
        try:
            parts = urlparse(params[a])
            if host and not parts.netloc:
                return 'A host is required in the URL: <scheme>://<host>/<path>'
            if scheme and not parts.scheme:
                return 'A scheme is required in the URL'
        except:
            return 'Not a correct URL'

    return check


def Verify(*rules):
    def check(params, errors=None):
        if errors is None:
            errors = {}

        results = dict(params)
        for r in rules:
            name_err = r(results)
            if name_err:
                errors[name_err[0]] = name_err[1]
        return results, errors

    return check


def joinElements(*args):
    return '\n'.join([a() if callable(a) else a for a in args])


def parseArguments(**kwargs):
    if 'klasse' in kwargs:
        kwargs['class'] = kwargs['klasse']
        del kwargs['klasse']
    return ' '.join('{}="{}"'.format(k, v) for k, v in kwargs.items())


def Link(target, label, **kwargs):
    args = parseArguments(**kwargs)
    return '<A {} HREF={}>{}</A>'.format(args, target, label)


def Container(tag, *children, **kwargs):
    options = parseArguments(**kwargs)
    contents = joinElements(*children)
    return '<{0} {1}>{2}</{0}>'.format(tag, options, contents)


def Div(*children, **kwargs):
    return Container('div', *children, **kwargs)


def Page(*args, refresh=None):
    body = joinElements(*args)
    headers = []
    if refresh:
        headers.append('<META HTTP-EQUIV="refresh" CONTENT="{}">'.format(refresh))
    return '''<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta http-equiv="X-UA-Compatible" content="IE=edge" />
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />
                <title>Overzichtgenerator</title>
            {header}
            <link rel="stylesheet" type="text/css" href="/static/css/bootstrap.min.css" />
            <link rel="stylesheet" type="text/css" href="/static/css/font-awesome.min.css" />
            <link rel="stylesheet" type="text/css" href="/static/css/custom-theme/jquery-ui-1.10.0.custom.css" />
            <link rel="stylesheet" type="text/css" href="/static/css/style.css" />
            <script src="/static/js/jquery/jquery-1.11.2.min.js"></script>
            <script src="/static/js/bootstrap/bootstrap.js"></script>


        </head>
        <body style="margin-top:0px">
        {body}
        </body>
        </html>
        '''.format(body=body,
                   header='\n'.join(headers))


def Title(text, tag='H1'):
    return '<{1} style="margin-top:0px">{0}</{1}>'.format(text, tag)


def ButtonBar(*args):
    buttons = ' '.join([b if isinstance(b, str) else b() for b in args])
    return '<div>{}</div>'.format(buttons)


def Button(caption, target='"#"', btn_type='primary', **kwargs):
    args = ' '.join('{}="{}"'.format(k, v) for k, v in kwargs.items())

    def get():
        btn_type_ = 'btn-{}'.format(btn_type) if isinstance(btn_type, str) else ' '.join(
            ['btn-{}'.format(t) for t in btn_type])
        return '<A HREF={} class="btn {}" {}>{}</A>'.format(target, btn_type_, args, caption)

    return get


def Lines(*args):
    """ Render the arguments as seperate lines
    """
    return '\n<BR>'.join(args)


def Pars(*args):
    """ Render the arguments as seperate paragraphs
    """
    return ''.join('<P>%s</P>\n' % a for a in args)


def Collapsibles(bodies, headers=None):
    def get():
        nonlocal headers
        if not headers:
            headers = ['>>>' for _ in bodies]
        hs = [Div(Link('#collapse%i' % i, header, **{'data-toggle': 'collapse'}),
                  klasse='panel-heading')
              for i, header in enumerate(headers)]
        bs = [Div(Div(a, klasse='panel-body'),
                  klasse='panel-colapse collapse',
                  id='collapse%i' % i) for i, a in enumerate(bodies)]
        return Div(*[Div(h, b, klasse="panel panel-default")
                     for h, b in zip(hs, bs)],
                   klasse='panel-group')

    return get


def SimpleForm(*args, validator=None, defaults={}, success=None, action='POST',
               submit='Opslaan', enctype="multipart/form-data", readonly=False, cancel=None,
               post_handler=None):
    def handle_simple_post(values, errors):
    # Handle the POST
    
    # If we are expecting input, validate it.
        # Check the suplied parameters for validity.

        # First call the validators linked to the individual inputs

        for a in args:
            if hasattr(a, 'validator'):
                values, errors = a.validator(values, errors)

        # Then call the global validator
        if validator:
            # Do NOT pass as keyword parameter: the validators will
            # change the values in request.params.
            values, errors2 = validator(values)
        else:
            values, errors2 = request_params(), {}

        errors.update(errors2)

        # Handle the action connected to the 'submit' phase of the form
        if not errors:
            # Call the success handler for each element
            for a in args:
                if hasattr(a, 'success'):
                    a.success(values)
        return values, errors

    post_handler = post_handler or handle_simple_post
    errors = {}
    values = request_params().copy()
    if request_method() in ['POST', 'PUT'] and action.upper() != 'DELETE':
        result = post_handler(values, errors)
        if isinstance(result, result_type):
            return result
    # In all cases where the form is submitted, perform the 'success' action.
    if request_method().upper() != 'GET' and not errors:
        result = success(**values)
        if result:
            return result
        defaults.update(values)

    path = request_path()

    # Determine which buttons to show
    if not success:
        btn = ''
    else:
        btns = ['<button class="btn btn-primary" type="submit" value="Submit">{}</button>'.format(
            submit)]
        if cancel:
            btns.insert(0, Button('Cancel', target=cancel))
        btn = ButtonBar(*btns)

    # Generate the actual HTML for the form
    base = '''
      <div class="container">
        <div class="row">
          <div class="col col-md-12">
            <form action="{action}" method="post" enctype="{enctype}" class="form-horizontal">
                {rows}
                <div class="col col-md-9 col-md-offset-3">
                    {btn}
                </div>
            </form>
          </div>
        </div>
      </div>
    '''
    row_base = '''
        <div class="form-group">
            <label class="col col-md-3 control-label">{label}</label>
            <div class="col col-md-9">{input}</div>
        </div>
    '''
    row_base_no_label = '''
        <div class="col col-md-9 col-md-offset-3">{input}</div>
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
        row = row.format(**input)
        rows.append(row)
    return base.format(rows='\n'.join(rows), action=path,
                       enctype=enctype, btn=btn)


def Hidden(name):
    def gen(defaults, errors, readonly):
        html = '<input type="hidden" name="{name}" value="{value}" />'
        return {'input': html.format(name=name, value=defaults.get(name, None))}

    return gen


def FileUpload(name, text=None):
    text = text or name
    return {'label': text,
            'input': '<input type="file" name="{}" />'.format(name)}


def MultiFileUpload(name, text=None):
    text = text or name
    return {'label': text,
            'input': '<input type="file" name="{}" multiple />'.format(name)}

def form_input(name, text, input_type, tmpl=None):
    base = tmpl or '<input type="{input_type}" class="form-control" name="{name}" {options} value="{default}"/>'
    text = text or name

    def gen(defaults, errors, readonly):
        nonlocal base
        default = defaults.get(name, '')
        error = errors.get(name, '')
        options = []
        if readonly:
            options.append('readonly')
        if error:
            base += '<div class="errmsg">{error}</div>'
        print(input_type)
        result = base.format(
            **{'input_type': input_type, 'name': name, 'error': error, 'default': default,
               'options': ' '.join(options)})
        return {'label': text, 'input': result}

    return gen


def Integer(name, text=None):
    return form_input(name, text, 'number')


def String(name, text=None):
    return form_input(name, text, 'text')


def Text(name, text=None):
    return form_input(name, text, '',
                      '<textarea name="{name}" {options} >{default}</textarea>')


def Tickbox(name, text=None):
    base = '<input type="checkbox" name="{}" value="True" {}>'
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
        result = base.format(name, ' '.join(options))
        return {'label': text, 'input': result}

    gen.success = onSuccess
    return gen


Server = Email = String


def EnterPassword(name, text=None):
    return form_input(PWD_FIELD_NAME, text, name)


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
                    'input': '<input class="form-control" readonly value="{}"/>'.format(value)}

        for i, o in enumerate(optionlist):
            if type(o) in [list, tuple]:
                value = (o[0], o[1])
            else:
                value = (o, o)
            final_options.append(value)
            if defaults.get(name, '') and value[1] == defaults[name]:
                index = i

        option_tags = ['<option value="{}">{}</option>'.format(*o) for o in final_options]
        if index:
            option_tags[i] = '<option selected="selected" value="{}">{}</option>'.format(
                final_options[i])
        args = 'name="{}"'.format(name)
        if readonly:
            args += ' readonly'
        return {'label': text,
                'input': '<select {}>'.format(args) + '\n'.join(option_tags) + '</select>'}

    return gen


def DownloadLink(name, path):
    return '<A HREF="{}" target="_blank">{}</A>'.format(path, name)


def PaginatedTable(line: Callable[[Any], Iterable[str]],
                   data: Iterable[Any],
                   header: Iterable[str] = None,
                   row_select_url: Callable[[Any], str] = None):
    ''' Shows a table. `line` is a function called with each record to return the columns for a row. It is
        called for each iteration from data.
        `data` is an iterable that is passed to the line generator.
        `header` is a list of strings that are placed as header above the table.
        `row_select_url` is a function that is called with the data for each row and returns an url
        to be triggered when the row is clicked.
    '''

    def get():
        head = ''
        if header:
            head = '<thead><tr>{}</tr></thead>'.format(
                '\n'.join('<th>{}</th>'.format(h) for h in header))
        parts = []
        thedata = data() if callable(data) else data
        for d in thedata:
            l = line(d) if line else d
            p = '\n'.join(['<td>{}</td>'.format(c) for c in l])
            oc = ''
            if row_select_url:
                su = row_select_url(d)
                oc = '''onclick="javascript:location.href='{}'"'''.format(su)
            parts.append('<tr {}>{}</tr>'.format(oc, p))
        b = '\n'.join(parts)
        return '<table class="table table-hover table-bordered">{}{}</table>'.format(head, b)

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
            if session_get('user_id', False):
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
        clean_path = defaults.get(name, '')
        img = ''
        if clean_path:
            img = '<img src="/static/{}">'.format(clean_path)
        if not readonly:
            img += '<input type="file" name="{}" />'.format(name)
        return {'label': label, 'input': img}

    gen.success = success
    return gen


field_factory = {int: Integer,
                 str: String,
                 bool: Tickbox}


def annotationsForm(cls, validator=None, success=None, readonly=False, extra_fields=None,
                    getter=None, prefix=''):
    """ Generate a form from the annotations in a data (message) class """
    fields = [field_factory[t](prefix + n, n) for n, t in cls.__annotations__.items()]
    if extra_fields:
        fields += extra_fields
    defaults = {n: getattr(cls, n) for n in cls.__annotations__ if hasattr(cls, n)}

    def gen():
        if getter:
            defaults.update(getter())
        return SimpleForm(*fields,
                          validator=validator,
                          defaults=defaults,
                          success=success,
                          readonly=readonly)

    return gen


def configEditor(*elements, validator=None, success=None, readonly=False, extra_fields=None,
                 getter: Callable, prefix=''):
    pass


def dummyacm(func):
    return func


def ACM(permissions, login_func):
    """ Return a decorator useful for controlling access.
    """

    def decorate(func):
        acm = permissions.get(func.__name__, False)

        def doit(*args, **kwargs):
            if not session_get('user_id', False):
                result = login_func(**kwargs)
                if not session_get('user_id', False):
                    # The user is NOT logged in.
                    return result
                # The user logged-in, we need to move to a fresh 'GET' request
                http_framework.cherrypy.request.method = 'GET'
                # Eval the arguments to allow Python-syntax arguments,
                # but do not allow access to local or global variables.
                kwargs = eval(kwargs['org_arg'], {}, {})
            role = session_get('role')
            if not acm or role in acm:
                return func(*args, **kwargs)
            raise http_framework.cherrypy.HTTPError(403, 'Action not allowed')

        return doit

    return decorate


def runServer(server, config={}):
    initial_config = {"/": {
        "tools.staticdir.debug": True,
        "tools.staticdir.root": os.path.join(os.path.dirname(__file__), '../../'),
        "tools.trailing_slash.on": True,
        "tools.staticdir.on": True,
        "tools.staticdir.dir": "./html"
    }}
    if config:
        initial_config.update(config)

    # cherrypy.log.access_log.propagate = False
    logging.getLogger('cherrypy_error').setLevel(logging.ERROR)

    http_framework.cherrypy.quickstart(server(), '/', initial_config)
