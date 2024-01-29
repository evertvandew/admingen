#!/usr/bin/env python3
""" render_word script

Reads a Word document that contains ${<define>} tags.
It reads definitions from stdin and from the command line to replace the tags with.

A special tag exists: if a 'define' is rendered to an `img(path/to/image)` text,
the tag is replaced by an image. Note that the template does NOT contain direct references
to the file system, because the template is expected to be user input.

The rendered file is either writen to standard output, or the file specified with the -o option.
"""
import re
try:
    import uno
except:
    raise RuntimeError("Please link the files /usr/lib/python3/dist-packages/uno.py en /usr/lib/python3/dist-packages/unohelper.py into the venv.")

from com.sun.star.awt import Size
from pythonscript import ScriptContext
import json
import sys
import os.path

import argparse

def open_template(template):
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    try:
        context = resolver.resolve("uno:socket,host=localhost,port=8100;urp;StarOffice.ComponentContext")
    except:
        raise RuntimeError("Coult not connect to soffice. Please start with e.g.:"
                           "\n/usr/bin/soffice --accept='socket,host=localhost,port=8100;urp;StarOffice.Service' --headless")
    desktop = context.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", context)

    # Load document template
    document = desktop.loadComponentFromURL(f"file://{template}", "_blank", 0, ())
    return document

def insert_image(doc, found, img_path):
    image = doc.createInstance( 'com.sun.star.drawing.GraphicObjectShape')
    image.GraphicURL = f"file://{img_path}"
    doc.Text.insertTextContent(found, image, 0)
    image.setPropertyValue('AnchorType', 'AS_CHARACTER')
    image.setSize(image.Graphic.Size100thMM)

def render(doc, parameters):
    # Search for the tags to be replaced.
    search = doc.createSearchDescriptor()
    search.SearchString = r"\$\{[^}]*\}"
    search.SearchRegularExpression = True

    found = doc.findFirst(search)
    while found:
        print("Found:", found.String)
        # Get the wrapped tag, removing the ${} wrapper
        tag = found.String[2:-1]

        replacement = parameters
        for a in tag.split('.'):
            if isinstance(replacement, dict):
                replacement = replacement.get(a, {})
            else:
                replacement = getattr(replacement, a, {})
        replacement = replacement or ''

        if isinstance(replacement, str) and replacement.startswith('img(') and replacement[-1] == ')':
            fname = replacement[4:-1]
            print("Rendering image", fname)
            insert_image(doc, found, fname)
            found.String = ''
        else:
            found.String = replacement

        # Find the next instance, if any.
        found = doc.findNext(found.End, search)


def run(args):
    """ Get the parameters, the open the template, render it and write to the output. """
    parameters = json.load(args.details)
    input = os.path.abspath(args.template)
    output = os.path.abspath(args.output)

    assert os.path.exists(input)

    doc = open_template(input)
    render(doc, parameters)

    print(f"Rendered {input}")

    # Store the rendered file
    doc.storeToURL(f'file://{output}', [])
    print(f"Writen to {output}")
    # Also store a PDF version for customers to download
    pdffile = os.path.abspath(os.path.splitext(args.output)[0] + '.pdf')
    doc.storeToURL(f'file://{pdffile}', [])
    doc.close(False)


def run_cli():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('template', help="Word template to be rendered.")
    parser.add_argument('output', help="Location where the file is writen to.")
    parser.add_argument('--details', '-d',
                        help="File containing details to be filled into the template. Default: stdin",
                        default=None)

    args = parser.parse_args()
    args.details = open(args.details) if args.details else sys.stdin
    run(args)

if __name__ == '__main__':
    run_cli()