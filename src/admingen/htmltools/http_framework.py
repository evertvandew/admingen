""" http framework support.
    Adds support for flask and also legacy support for cherrypy.
    We moved away from cherrypy because flask has a functional design and is more
    popular than cherrypy.
"""

# Try to import cherrypy
success = False
try:
    import cherrypy

    def request_method():
        return cherrypy.request.method
    def request_params():
        return cherrypy.request.params
    def request_path():
        return cherrypy.request.path_info
    def session_get(name, default=None):
        return cherrypy.session.get(name, default)

    result_type = str

    success = True
except ImportError:
    pass

if not success:
    try:
        import flask
        def request_method():
            return flask.request.method
        def request_params():
            if flask.request.form:
                return flask.request.form
            return flask.request.args
        def request_path():
            return flask.request.path
        def session_get(name, default=None):
            """ Assume we use client-side cookies for session info.
                TODO: This is not as safe as server-side sessions.
            """
            return flask.request.cookies.get(name, default)

        result_type = flask.Response

        success = True
    except ImportError:
        pass

assert success, "Could not load an http framework"