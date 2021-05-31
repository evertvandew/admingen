#!/usr/bin/env python3
""" Convert a multi-tab Excel file to a CSV file in my database form.
"""
import os.path
import sys

try:
    import uno
except:
    raise RuntimeError("Please link the files /usr/lib/python3/dist-packages/uno.py en /usr/lib/python3/dist-packages/unohelper.py into the venv.")

from admingen.data import CsvWriter

from com.sun.star.awt import Size
from pythonscript import ScriptContext


#CsvWriter(sys.stdout, {'A': [[1,2,3,4,5], [43,56,32,6,3]]})

def open_template(fname):
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    try:
        context = resolver.resolve("uno:socket,host=localhost,port=8100;urp;StarOffice.ComponentContext")
    except:
        raise RuntimeError("Coult not connect to soffice. Please start with e.g.:"
                           "\n/usr/bin/soffice --accept='socket,host=localhost,port=8100;urp;StarOffice.Service' --headless")
    desktop = context.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
    # Load document template
    fname = os.path.abspath(fname)
    document = desktop.loadComponentFromURL(f"file://{fname}", "_blank", 0, ())
    return document


doc = open_template('details.ods')
ss = doc.getSheets()

max_cols = 100


all_sheets = {}
for sheet in ss:
    name = sheet.Name
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
            if empty_cols > 10:
                break
        # Prune empty cells
        first_nonempty = 0
        for i, v in reversed(list(enumerate(row_data))):
            if v:
                first_nonempty = i
                break
        row_data = row_data[:first_nonempty]
        sheet_data.append(row_data)
        if not row_data:
            empty_lines += 1
        else:
            empty_lines = 0
        if empty_lines > 10:
            break
        row += 1
    all_sheets[name] = sheet_data

CsvWriter(sys.stdout, all_sheets)
