
import sys
from admingen.data import filter
from io import StringIO
from unittest import TestCase, main


class tests(TestCase):
    def test1(self):
        out = StringIO()
        filter(open('urendata.csv'),
               open('process_factuur').read(),
               out,
               {'period' : '201804',
                'opdracht' : 2})
        output = out.getvalue()
        output_lines = [l for l in output.split('\n') if not l.startswith('datum')]
        reference = open('urendata.yaml').read()
        ref_lines = [l for l in reference.split('\n') if not l.startswith('datum')]

        self.assertEqual(output_lines, ref_lines)

if __name__ == '__main__':
    main()
