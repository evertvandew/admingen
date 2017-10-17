"""
The message protocol is very simple: All messages have the following format:

<msg_id> <msg_name> <msg_body>
.

Messages are terminated by a line containing only a period.
Message bodies can be multi-line, with no restrictions in character content.

"""

from collections import namedtuple
from io import StringIO

msg_type = namedtuple('msg_type', ['id', 'name', 'body'])

def scanner(stream):
    """ A generator that reads messages from a stream """
    for header in stream:
        if not header or header == '\n':
            continue
        parts = header.split(maxsplit=2)
        if len(parts) < 2:
            raise RuntimeError('Malformed message')
        ID = parts[0]
        name = parts[1]
        body_parts = [parts[2]] if len(parts) == 3 else []

        for line in stream:
            if line == '.\n':
                yield msg_type(ID, name, ''.join(body_parts))
                break
            body_parts.append(line)


testmsgs = '''A0000 BLAAT
.


A0001 USER "frobozz" "xyzzy"
.
A0003 FETCH 1 RFC822.SIZE                    Get message sizes
FETCH (RFC822.SIZE 2545)
.
'''

if __name__ == '__main__':
    f = StringIO(testmsgs)
    for parts in scanner(f):
        print (parts)
