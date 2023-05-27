"""
A module for generating SVG documents, compatible with the Brython SVG API.
"""
from typing import Dict, List


def svgAttrName(key):
    """ Determine the name of an svg attribute, translating from what is acceptable as a Python argument. """
    # Arguments can not have dashes, they are replaced by underscores.
    return key.replace('_', '-')


class RenderedElement:
    def __init__(self, name: str, attributes: Dict[str, str], innerhtml: List[str], attribute_keys):
        self.name = name
        self.attributes = attributes
        self.innerhtml = innerhtml if isinstance(innerhtml, list) else [innerhtml]
        self.attribute_keys = attribute_keys
    def __le__(self, innerhtml):
        if isinstance(innerhtml, list):
            self.innerhtml.extend(str(l) for l in innerhtml)
        else:
            self.innerhtml.append(str(innerhtml))
        pass
    def __setitem__(self, key, value):
        self.attributes[key] = value
    def render(self):
        style = {k:v for k, v in self.attributes.items() if k not in self.attribute_keys}
        style = ';'.join(f'{svgAttrName(k)}:{v}' for k, v in style.items())
        attributes = {k:v for k, v in self.attributes.items() if k in self.attribute_keys}
        attributes['style'] = style
        attrs = ' '.join(f'{svgAttrName(k)}="{v}"' for k, v in attributes.items())
        innerhtml = '\n'.join(self.innerhtml)
        return f'<{self.name} {attrs}>{innerhtml}</{self.name}>'
    def __str__(self):
        return self.render()


def generate_svg_shape(element, attributes):
    attribute_keys = attributes.split()
    def doIt(*args, **kwargs):
        args = [a if isinstance(a, str) else a.render() for a in args]
        return RenderedElement(element, kwargs, args, attribute_keys)
    return doIt


_definitions = {
    'a': 'href',
    'circle': 'cx cy r',
    'ellipse': 'cx cy rx ry pathLength',
    'g': '',
    'line': 'x1 x2 y1 y2 marker_start',
    'path': 'd pathLength',
    'poly': 'points pathLength',
    'polyline': 'points pathLength',
    'rect': 'x y width height rx ry',
    'text': 'x y dx dy rotate lengthAdjust textLength',
    'textpath': 'href lengthAdjust method path side spacing startOffset textLength',
}

for name, details in _definitions.items():
    globals()[name] = generate_svg_shape(name, details)

class svg(RenderedElement):
    def __init__(self):
        super().__init__('svg', {}, [], [])
        self.viewBox = [0, 0, 800, 500]

    def render(self):
        innerhtml = '\n'.join(self.innerhtml)
        viewbox = ' '.join(str(i) for i in self.viewBox)
        return f'''<svg width="100%" height="100%" viewBox="{viewbox}"  xmlns="http://www.w3.org/2000/svg" >
{innerhtml}
</svg>'''