
from unittest import TestCase

import cherrypy
from admingen.htmltools import AnnotationsForm

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
        form = AnnotationsForm(TestClass, validator, success)

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


