

from unittest import TestCase
from io import StringIO
from admingen.reporting import render_stream

class tests(TestCase):
    def testFactuur(self):
        out = StringIO()
        render_stream(open('urendata.yaml'),
                      open('../templates/factuur.fodt'),
                      out)
        with open('test.fods', 'w') as outf:
            outf.write(out.getvalue())
