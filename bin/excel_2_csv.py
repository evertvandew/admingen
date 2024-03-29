#!/usr/bin/env python3
""" Convert a multi-tab Excel file to a CSV file in my database form.

Currently, empty lines are always removed. If this is unwanted in the future, add a switch.
"""
import os.path
import sys
import argparse

try:
    import uno
except:
    raise RuntimeError("Please link the files /usr/lib/python3/dist-packages/uno.py en /usr/lib/python3/dist-packages/unohelper.py into the venv.")

from admingen.data import CsvWriter


def open_template(fname):
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    try:
        context = resolver.resolve("uno:socket,host=localhost,port=8100;urp;StarOffice.ComponentContext")
    except:
        raise RuntimeError("Could not connect to soffice. Please start with e.g.:"
                           "\n/usr/bin/soffice --accept='socket,host=localhost,port=8100;urp;StarOffice.Service' --headless")
    desktop = context.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
    # Load document template
    fname = os.path.abspath(fname)
    document = desktop.loadComponentFromURL(f"file://{fname}", "_blank", 0, ())
    return document


parser = argparse.ArgumentParser()
parser.add_argument('input', help='Input file (ODS spreadsheet)')
parser.add_argument('--sparse', '-s', nargs='*', help='Sheets that contain sparse matrices')
parser.add_argument('--max_cols', '-m', default=1000, help='Maximum columns in any sheet')
args = parser.parse_args()


doc = open_template('details.ods')
ss = doc.getSheets()

max_cols = 1000


all_sheets = {}
for sheet in ss:
    name = sheet.Name
    is_sparse = sheet.Name in args.sparse
    print("Reading sheet", name, file=sys.stderr)
    row = 0
    sheet_data = []
    empty_lines = 0
    while True:
        row_data = []
        empty_cols = 0
        for col in range(max_cols):
            s = sheet.getCellByPosition(col, row).String
            row_data.append(s)
            if not(s):
                empty_cols += 1
            else:
                empty_cols = 0
            if empty_cols > 10 and not is_sparse:
                break
        # Prune empty cells
        first_nonempty = -1
        for i, v in reversed(list(enumerate(row_data))):
            if v:
                first_nonempty = i
                break
        row_data = row_data[:first_nonempty+1]
        if not row_data:
            empty_lines += 1
        else:
            sheet_data.append(row_data)
            empty_lines = 0
        if empty_lines > 10:
            break
        row += 1
    all_sheets[name] = sheet_data

CsvWriter(sys.stdout, all_sheets)
