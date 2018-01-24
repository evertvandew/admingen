
from unittest import TestCase

import cherrypy
from admingen.htmltools import *


lorem = '''Lorem ipsum dolor sit amet, consectetur adipiscing elit, 
sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. 
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris 
nisi ut aliquip ex ea commodo consequat.<BR> 
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum 
dolore eu fugiat nulla pariatur.<BR>
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia 
deserunt mollit anim id est laborum.'''


class HtmlTests(TestCase):

    def testAnnotationForm(self):

        class TestClass:
            field_a: int
            field_b: str = 'a default'



        def validator():
            return {'field_a': 1234, 'field_b': 'test'}, {}

        def success(field_a, field_b):
            if field_a==1234 and field_b == 'test':
                return 'OK'

        # Create the form
        form = annotationsForm(TestClass, validator, success)

        # test the 'GET'
        html = form()
        self.assertTrue('<input type="text" class="form-control" name="field_b"  value="a default"/>' in html)
        self.assertTrue('<input type="number" class="form-control" name="field_a"  value=""/>' in html)

        # test the 'POST'
        r = cherrypy.request
        r.method = 'POST'
        r.path = '/'
        html = form()
        self.assertEqual(html, 'OK')

    def testCollapsible(self):
        bodies = [(Title('Collapsible %i'%(i+1)) + lorem) for i in range(3)]
        headers = [Title('Header %i'%(i+1), 'H4') for i, _ in enumerate(bodies)]
        print (Page(Collapsibles(bodies, headers)()))

