

import flask
import glob
import os, os.path
from PIL import Image

prefix = '/sonneveld_vakantie'


app = flask.Flask(__name__)


if not os.path.exists('photos'):
    os.mkdir('photos')
if not os.path.exists('thumbs'):
    os.mkdir('thumbs')


@app.route(f'{prefix}/upload', methods=['POST'])
def upload():
    files = flask.request.files.getlist("imgs")
    for pic in files:
        if not pic.filename:
            continue
        fname1 = f'photos/{pic.filename}'
        pic.save(fname1)
        img = Image.open(fname1)
        img.thumbnail((128, 128))
        fname2 = f'thumbs/{pic.filename}'
        img.save(fname2)

    return flask.redirect(f'{prefix}')

@app.route(f'{prefix}/photos/<pic>')
def get_pic(pic):
    return flask.send_from_directory(directory='photos', filename=pic)

@app.route(f'{prefix}/thumbs/<pic>')
def get_thumb(pic):
    return flask.send_from_directory(directory='thumbs', filename=pic)


@app.route(prefix)
def index():
    pics = os.listdir('photos')
    return flask.render_template('photos.html', prefix=prefix, pics=pics)


@app.route('/batic/<path:path>')
def send_js(path):
    return flask.send_from_directory('batic', path)


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
