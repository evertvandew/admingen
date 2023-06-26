
import enum
from copy import copy
import tatsu
from admingen.data.dummy_db import DummyDatabase
from admingen.data.data_type_base import mydataclass


class Rol(enum.IntEnum):
    administrator = 0
    editor = 1
    user = 2


@mydataclass
class Bedrijf:
    id: int
    naam: str
    omschrijving: str


@mydataclass
class User:
    id: int
    login: str
    password: str
    rol: int
    email: str
    vollenaam: str
    bedrijf: int
    klant: int


# First some mocks
class MockRequest:
    cookies = {}
    remote_addr = '127.0.0.1'
    path = '/'
    method = 'GET'
    data = {}
    args = {'encoding': ''}

    @staticmethod
    def set_data(data):
        MockRequest.data = data
        MockRequest.form = data
        MockRequest.values = data

    @staticmethod
    def set_cookies(data):
        for c, v in list(data.items()):
            if not isinstance(c, str):
                c = c.decode('utf8')
            if type(v) not in [str, bytes, bytearray]:
                v = str(v)
            MockRequest.cookies[c] = v


class MockHeaders:
    headers = []

    @staticmethod
    def add(key, value):
        MockHeaders.headers.append((key, value))


class MockResponse:
    text = ''
    code = -1
    cookies = {}
    headers = MockHeaders

    @staticmethod
    def set_cookie(name, value, max_age=-1):
        MockResponse.cookies[name] = value

    @staticmethod
    def delete_cookie(name):
        if name in MockResponse.cookies:
            del MockResponse.cookies[name]


class HttpError(RuntimeError):
    def __init__(self, code):
        super().__init__(self, "HTTP error")
        self.code = code


class MockFlask:
    request = MockRequest

    @staticmethod
    def make_response(msg, code):
        MockResponse.text = msg
        MockResponse.code = code
        return MockResponse

    @staticmethod
    def abort(code):
        raise HttpError(code)


class MockDb:
    all_tables = {'testdb': [User, Bedrijf]}
    db = DummyDatabase(all_tables['testdb'])

    @staticmethod
    def setRecords(records):
        def doIt():
            MockDb.db.clear()
            for record in records:
                MockDb.db.set(copy(record))

        return doIt


class MockApp:
    routes = []
    befores = []
    all_tables = MockDb.all_tables
    context = {'databases': {'testdb': MockDb.db},
               'datamodel': all_tables}
    db = context['databases']['testdb']
    acm = None
    path_ebnf = '''
        path = '/' .{ part } ;
        part =  variable | constant ;
        constant = /[a-zA-Z0-9_.]*/ ;
        variable = "<" ('int' | 'str' ) ":" constant ">" ;
    '''
    path_parser = tatsu.compile(path_ebnf, 'path')

    @staticmethod
    def route(path, methods=['GET']):
        path_ast = MockApp.path_parser.parse(path)
        def route_setter(f):
            def matcher(p, m):
                arguments = {}
                parts = p.split('/')
                if len(parts) != len(path_ast):
                    return

                for i, element in enumerate(path_ast):
                    if isinstance(element, str):
                        # constant part
                        if parts[i] != element:
                            return
                    else:
                        # variable part
                        caster = {'int': int, 'str': str}[element[1]]
                        varname = element[3]
                        arguments[varname] = caster(parts[i])

                try:
                    match result := f(**arguments):
                        case MockResponse():
                            return result
                        case str(msg):
                            return MockFlask.make_response(msg, 200)
                        case (str(msg), int(code)):
                            return MockFlask.make_response(msg, code)
                except HttpError as e:
                    return MockFlask.make_response("Could not handle request", e.code)


            MockApp.routes.append(matcher)

        return route_setter

    @staticmethod
    def before_request(f):
        MockApp.befores.append(f)

    @staticmethod
    def request(path, method='GET', data=None):
        print("Routing:", path)
        MockRequest.path = path
        MockRequest.method = method
        MockResponse.code = 0
        if data:
            MockRequest.set_data(data)
        for b in MockApp.befores:
            b()
        for f in MockApp.routes:
            f(path, method)


if __name__ == '__main__':
    # Some tests used during development

    def testRouteMatching():
        calls_list = []
        def index():
            calls_list.append('index')
        def explicit_index():
            calls_list.append('explicit_index')
        def data_index(table, id):
            calls_list.append(f'data {table} {id}')
        MockApp.route('/')(index)
        MockApp.route('/index.html')(explicit_index)
        MockApp.route('/data/<str:table>/<int:id>')(data_index)

        MockApp.request('/')
        MockApp.request('/index.html')
        MockApp.request('/data/User/2345')
        MockApp.request('/data/Company/876')
        MockApp.request('/non-existing')

        assert calls_list == ['index', 'explicit_index', 'data User 2345', 'data Company 876']

    testRouteMatching()
