#!/usr/bin/env python3
import xml.etree.ElementTree as ET


root = ET.parse('test2.xml')

for glt in root.findall('.//GLTransaction'):
    for line in glt.findall('.//GLTransactionLine'):
        v1 = line.find('./Amount/Value')
        v2 = line.find('./ForeignAmount/Value')
        r  = line.find('./ForeignAmount/Rate')
        parts = [line.find('./Date').text,
                 v1.text if v1 is not None else '',
                 v2.text if v2 is not None else '',
                 r.text if r is not None else ''
                 ]
        print (','.join(parts))
