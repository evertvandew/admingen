from flask import Flask, send_from_directory

app = Flask(__name__, static_url_path='')


# We need a number of routes:
# 1. The route for files in the resources area
# 2. The catch-all routes for documents and directories: GET, POST, PUT, DELETE
# 3. The system functions for login and user management


# First we need the resources area
@app.route('/resources/<path:path>')
def send_resource(path):
    return send_from_directory('resources', path)


# Then we need the route for viewing documents & directories

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return 'You want path: %s' % path

if __name__ == '__main__':
    app.run()
