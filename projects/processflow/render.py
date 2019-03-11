import re
import markdown
from markdown.extensions.tables import TableExtension

FILEDIR = '/home/ehwaal/tmp/processflow'


def textinput(m):
    name = m.groupdict()['name']
    s = '''<label for="{0}">{1}:</label>
    <input type="text" id="{0}" name="{0}" size="20"/>'''
    return s.format(name.lower(), name)


def radiobuttons(m):
    details = m.groupdict()
    name = details['name']
    options = re.findall(r'\([*xX]?\)\s*[^|()[\]{}]+', details['details'])
    txt = ['<label for="{0}">{1}:</label>'.format(name.lower(), name)]
    for o in options:
        value = o.split(maxsplit=1)[1]
        s = '<input type="radio" name="{0}" id="{2}" value="{2}" %s/><label for="{2}">{3}</label>'
        if o[1] in '*xX':
            s = s % 'checked="checked"'
        else:
            s = s % ''

        txt.append(s.format(name.lower(), name, value.lower(), value))
    return '\n'.join(txt)


def checkbuttons(m):
    details = m.groupdict()
    name = details['name']
    options = re.findall(r'\[[*xX]?\]\s*[^|()[\]{}]+', details['details'])
    txt = ['<label for="{0}">{1}:</label>'.format(name.lower(), name)]
    for o in options:
        value = o.split(maxsplit=1)[1]
        s = '<input type="checkbox" name="{0}" id="{2}" value="{2}" %s/><label for="{2}">{3}</label>'
        if o[1] in '*xX':
            s = s % 'checked="checked"'
        else:
            s = s % ''

        txt.append(s.format(name.lower(), name, value.lower(), value))
    return '\n'.join(txt)


def selection(m):
    details = m.groupdict()
    name = details['name']
    options = re.findall(r'[^{},]+', details['details'])
    parts = ['''<label for="{0}">{1}:</label>
             <select id="{0}" name="{0}">'''.format(name.lower(), name)]
    for o in options:
        value = o.strip('{}(), ')
        sel = ' selected="selected"' if '(' in o else ''
        s = '<option value="{0}"{1}>{0}</option>'.format(value, sel)
        parts.append(s)
    parts.append('</select>')
    return '\n'.join(parts)


def input_preprocess(text):
    """ Find any extended tags that are transformed into input fields """
    name = r'\s*(?P<name>[^|()[\]*]*)(?P<required>\*?)\s*=\s*(?P<details>%s)'
    buttons = r'(%s[*xX]?%s\s*[^|()[\]{}]+)+'
    signatures = [(name % r'___+', textinput),
                  (name % (buttons % ('\(', '\)')), radiobuttons),
                  (name % (buttons % ('\[', '\]')), checkbuttons),
                  (name % r'\{[^{}]+\}', selection),
                  ]
    for line in text.splitlines():
        while True:
            m = None
            for ptrn, func in signatures:
                m = re.search(ptrn, line)
                if m:
                    # Yield the bit before the pattern (if any)
                    yield line[:m.span()[0]]
                    # Yield the input item
                    yield func(m)
                    line = line[m.span()[1]:]
                    break
            if m is None:
                # No match found.
                # Yield the rest of the line
                yield line
                break


def test():
    t = '''<html>
    <body>
    name = ___
    sex = (x) male () female
    phones = [] Android [x] iPhone [x] Blackberry
    city = {BOS, SFO, (NYC)}
    </body>
    </html>
    '''
    print('\n'.join(input_preprocess(t)))


def run():
    txt = open(FILEDIR + '/documents/forms/schouwing.md').read()
    txt = input_preprocess(txt)
    print(markdown.markdown(txt, extensions=[TableExtension()]))


test()