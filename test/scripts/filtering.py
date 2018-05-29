
import sys
from admingen.data import filter


filter(open('urendata.csv'),
       open('process_factuur').read(),
       sys.stdout,
       {'period' : '201804',
        'opdracht' : 2})
