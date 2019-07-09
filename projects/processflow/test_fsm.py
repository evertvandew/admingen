
from subprocess import Popen, PIPE
import os

testscript = b'''> Please login
< login admin testing
> Welcome, admin

< add {'title': 'Testdocument', 'type': 'testdocument'}
> 1

'''


p = Popen("~/admingen/bin/fsm.py", shell=True, stdin=PIPE, stdout=PIPE)

for line in testscript.splitlines(keepends=False):
    if not line:
        continue
    direction, l = line.strip().split(maxsplit=1)
    if direction == b'>':
        # Check the output
        print ('got', os.read(p.stdout.fileno(), 4096))
    elif direction == b'<':
        os.write(p.stdin.fileno(), l+b'\n')
        print('written', l)


