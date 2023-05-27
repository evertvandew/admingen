

import enum
from admingen.htmltools import svg
from admingen.htmltools.fontsizes import font_sizes
from itertools import chain


###############################################################################
# Support for rendering text
class VAlign(enum.IntEnum):
    TOP = 1
    CENTER = 2
    BOTTOM = 3

class HAlign(enum.IntEnum):
    LEFT = 10
    CENTER = 11
    RIGHT = 12
    JUSTIFIED = 13

POINT_TO_PIXEL = 1.3333

def wrapText(text, width, font='Arial.ttf', fontsize='10'):
    # Separate into words and determine the size of each part
    font = font_sizes['Arial.ttf']['sizes']
    parts = text.split()
    normalized_width = width / POINT_TO_PIXEL / fontsize
    sizes = [sum(font.get(ord(ch), font[32]) for ch in part) for part in parts]

    # Now fill the lines
    line_length = 0
    lines = []
    current_line = []
    for size, part in zip(sizes, parts):
        if line_length + size + font[32]*(len(current_line)-1) > normalized_width:
            lines.append(' '.join(current_line))
            current_line = []
            line_length = 0
        current_line.append(part)
        line_length += size
    if current_line:
        lines.append(' '.join(current_line))
    return lines

def renderText(text, d):
    font_file = d.getStyle('font', 'Arial')+'.ttf'
    fontsize = float(d.getStyle('fontsize', 12))
    lines = wrapText(text, d.width, font_file, fontsize)
    # Now render these lines
    anchor = {HAlign.LEFT: 'start', HAlign.CENTER: 'middle', HAlign.RIGHT: 'end'}[d.getStyle('halign', HAlign.LEFT)]
    lineheight = font_sizes[font_file]['lineheight'] * fontsize * float(d.getStyle('linespace', '1.2'))
    # Calculate where the text must be placed.
    xmargin = int(d.getStyle('xmargin', '5'))
    xpos = int({HAlign.LEFT: d.x+xmargin, HAlign.CENTER: d.x+d.width/2, HAlign.RIGHT: d.x+d.width-xmargin}[d.getStyle('halign', HAlign.LEFT)])
    ypos = {#VAlign.TOP: y+ymargin,
            VAlign.CENTER: d.y+(d.height-len(lines)*lineheight)/2
            #VAlign.BOTTOM: y+height-len(lines)*lineheight*fontsize - ymargin
           }[d.getStyle('valign', VAlign.CENTER)]

    rendered = [svg.text(line, x=xpos, y=int(ypos+lineheight*(i+1)), text_anchor=anchor, font_size=fontsize, font_family=d.getStyle('font', 'Arial'))
                for i, line in enumerate(lines)]
    return rendered


###############################################################################
# Some predetermined shapes

class BasicShape:
    style_items = {'bordercolor': 'black', 'bordersize': '2', 'blockcolor': 'white'}
    @classmethod
    def getShape(cls, details):
        raise NotImplementedError
    @classmethod
    def updateShape(cls, shape, details):
        raise NotImplementedError
    @staticmethod
    def getDescriptor(name):
        name = name.lower()
        for cls in BasicShape.getShapeTypes():
            if cls.__name__.lower() == name.lower():
                return cls
        raise RuntimeError(f"Unknown shape type {name}")
    @classmethod
    def getShapeTypes(cls):
        return cls.__subclasses__() + list(chain.from_iterable(c.getShapeTypes() for c in cls.__subclasses__()))

    @classmethod
    def getType(cls):
        return cls.__name__.lower()

    @classmethod
    def getStyle(cls, key, details):
        # Find a default value for the style item
        default = cls.style_items.get(key, None)
        if default is None:
            for c in cls.mro():
                if key in c.style_items:
                    default = c.style_items[key]
                    break
        return details.getStyle(key, default)


class Rect(BasicShape):
    style_items = {'cornerradius': '0'}
    @classmethod
    def getShape(cls, details):
        return svg.rect(x=details.x, y=details.y, width=details.width, height=details.height,
                        stroke_width=cls.getStyle('bordersize', details),
                        stroke=cls.getStyle('bordercolor', details),
                        fill=cls.getStyle('blockcolor', details),
                        ry=cls.getStyle('cornerradius', details))
    @classmethod
    def updateShape(cls, shape, details):
        shape['width'], shape['height'] = details.width, details.height
        shape['x'], shape['y'] = details.x, details.y
        shape['ry'] = cls.getStyle('cornerradius', details)
        stroke_width = cls.getStyle('bordersize', details)
        stroke = cls.getStyle('bordercolor', details)
        fill = cls.getStyle('blockcolor', details)
        shape['style'] = f"stroke_width:{stroke_width}; stroke:{stroke}; fill:{fill}"

class Circle(BasicShape):
    style_items = {}
    @classmethod
    def getShape(cls, details):
        return svg.circle(cx=details.x+details.width//2, cy=details.y+details.height//2,
                        r=(details.width+details.height)//4,
                        stroke_width=cls.getStyle('bordersize', details),
                        stroke=cls.getStyle('bordercolor', details),
                        fill=cls.getStyle('blockcolor', details))
    @classmethod
    def updateShape(cls, shape, details):
        shape['r'] = (details.width + details.height) // 4
        shape['cx'], shape['cy'] = details.x+details.width//2, details.y+details.height//2
        stroke_width = cls.getStyle('bordersize', details)
        stroke = cls.getStyle('bordercolor', details)
        fill = cls.getStyle('blockcolor', details)
        shape['style'] = f"stroke_width:{stroke_width}; stroke:{stroke}; fill:{fill}"

class Ellipse(BasicShape):
    style_items = {}
    @classmethod
    def getShape(cls, details):
        return svg.ellipse(cx=details.x+details.width//2, cy=details.y+details.height//2,
                        rx=details.width//2, ry=details.height//2,
                        stroke_width=cls.getStyle('bordersize', details),
                        stroke=cls.getStyle('bordercolor', details),
                        fill=cls.getStyle('blockcolor', details))
    @classmethod
    def updateShape(cls, shape, details):
        shape['rx'], shape['ry'] = details.width//2, details.height//2
        shape['cx'], shape['cy'] = details.x+details.width//2, details.y+details.height//2
        stroke_width = cls.getStyle('bordersize', details)
        stroke = cls.getStyle('bordercolor', details)
        fill = cls.getStyle('blockcolor', details)
        shape['style'] = f"stroke_width:{stroke_width}; stroke:{stroke}; fill:{fill}"

class Note(BasicShape):
    style_items = {'fold_size': '10'}
    @classmethod
    def getPoints(cls, details):
        x, y, w, h = details.x, details.y, details.width, details.height
        f = int(cls.getStyle('fold_size', details))
        return [(x+a,y+b) for a, b in [(0,0), (w-f,0), (w,f), (w-f,f), (w-f,0), (w,f), (w,h), (0,h), (0,0)]]
    @classmethod
    def getShape(cls, details):
        outline = svg.polyline(points=' '.join(f'{x},{y}' for x, y in cls.getPoints(details)),
                              fill=cls.getStyle('blockcolor', details), stroke=cls.getStyle('bordercolor', details),
                              stroke_width=cls.getStyle('bordersize', details))
        return outline
    @classmethod
    def updateShape(cls, shape, details):
        shape['points'] = ' '.join(f'{x},{y}' for x, y in cls.getPoints(details))
        stroke_width = cls.getStyle('bordersize', details)
        stroke = cls.getStyle('bordercolor', details)
        fill = cls.getStyle('blockcolor', details)
        shape['style'] = f"stroke_width:{stroke_width}; stroke:{stroke}; fill:{fill}"

class Component(BasicShape):
    style_items = {'ringwidth': '15', 'ringheight': '10', 'ringpos': '25', 'cornerradius': '0'}
    @classmethod
    def getShape(cls, details):
        g = svg.g()
        # Add the basic rectangle
        g <= Rect.getShape(details)
        # Add the two binder rings
        rw, rh, rp = [int(cls.getStyle(i, details)) for i in 'ringwidth ringheight ringpos'.split()]
        rp = rp * details.height // 100
        g <= svg.rect(x=details.x-rw//2,
                      y=details.y+rp,
                      width=cls.getStyle('ringwidth', details),
                      height=cls.getStyle('ringheight', details),
                      stroke_width=cls.getStyle('bordersize', details),
                      stroke=cls.getStyle('bordercolor', details),
                      fill=cls.getStyle('blockcolor', details))
        g <= svg.rect(x=details.x-rw//2,
                      y=details.y+details.height-rp-rh,
                      width=cls.getStyle('ringwidth', details),
                      height=cls.getStyle('ringheight', details),
                      stroke_width=cls.getStyle('bordersize', details),
                      stroke=cls.getStyle('bordercolor', details),
                      fill=cls.getStyle('blockcolor', details))
        return g
    @classmethod
    def updateShape(cls, shape, details):
        # Update the large square
        Rect.updateShape(shape.children[0], details)
        # Update the rings
        rw, rh, rp = [int(cls.getStyle(i, details)) for i in 'ringwidth ringheight ringpos'.split()]
        rp = rp * details.height // 100
        r1, r2 = shape.children[1:]
        r1['x'] = details.x-rw//2
        r2['x'] = details.x-rw//2
        r1['y'] = details.y+rp
        r2['y'] = details.y+details.height-rp-rh
        stroke_width = cls.getStyle('bordersize', details)
        stroke = cls.getStyle('bordercolor', details)
        fill = cls.getStyle('blockcolor', details)
        style = f"stroke_width:{stroke_width}; stroke:{stroke}; fill:{fill}"
        for child in shape.children:
            child['style'] = style

class Diamond(Note):
    @classmethod
    def getPoints(cls, details):
        return [(details.x+a, details.y+b) for a, b in [
            (details.width//2,0),
            (details.width,details.height//2),
            (details.width//2,details.height),
            (0,details.height//2),
            (details.width//2,0)]]

class ClosedCircle(Circle):
    @classmethod
    def getShape(cls, details):
        shape = Circle.getShape(details)
        shape['fill'] = cls.getStyle('bordercolor', details)
        return shape
    @classmethod
    def updateShape(cls, shape, details):
        Circle.updateShape(shape, details)
        stroke_width = cls.getStyle('bordersize', details)
        stroke = cls.getStyle('bordercolor', details)
        shape['style'] = f"stroke_width:{stroke_width}; stroke:{stroke}; fill:{stroke}"

class RingedClosedCircle(BasicShape):
    style_items = {'space': '25'}
    @classmethod
    def getShape(cls, details):
        r = (details.width + details.height) // 4
        space = int(cls.getStyle('space', details)) * r // 100
        ball = ClosedCircle.getShape(details)
        ball['r'] = r - space
        ring = Circle.getShape(details)
        ring['fill'] = 'none'
        g = svg.g()
        g <= ball
        g <= ring
        return g
    @classmethod
    def updateShape(cls, shape, details):
        r = (details.width + details.height) // 4
        space = int(cls.getStyle('space', details)) * r // 100
        ClosedCircle.updateShape(shape.children[0], details)
        Circle.updateShape(shape.children[1], details)
        shape.children[0]['r'] = r - space

class Bar(Rect):
    style_items = {'blockcolor': 'black'}
    @classmethod
    def getShape(cls, details):
        return svg.rect(x=details.x, y=details.y, width=details.width, height=details.height,
                        stroke_width=cls.getStyle('bordersize', details),
                        stroke=cls.getStyle('blockcolor', details),
                        fill=cls.getStyle('blockcolor', details),
                        ry=cls.getStyle('cornerradius', details))
    @classmethod
    def updateShape(cls, shape, details):
        shape['width'], shape['height'] = details.width, details.height
        shape['x'], shape['y'] = details.x, details.y
        shape['ry'] = cls.getStyle('cornerradius', details)
        stroke_width = cls.getStyle('bordersize', details)
        stroke = cls.getStyle('blockcolor', details)
        fill = cls.getStyle('blockcolor', details)
        shape['style'] = f"stroke_width:{stroke_width}; stroke:{stroke}; fill:{fill}"


class Hexagon(Note):
    style_items = {'bump': '15'}
    @classmethod
    def getPoints(cls, details):
        bump = int(cls.getStyle('bump', details))
        return [(details.x+a, details.y+b) for a, b in [
            (0, 0),
            (details.width, 0),
            (details.width+bump, details.height//2),
            (details.width, details.height),
            (0, details.height),
            (-bump, details.height//2),
            (0,0)]]

class Octagon(Hexagon):
    @classmethod
    def getPoints(cls, details):
        bump = int(cls.getStyle('bump', details))
        return [(details.x+a, details.y+b) for a, b in [
            (0, 0),
            (details.width, 0),
            (details.width+bump, details.height//4),
            (details.width+bump, 3*details.height//4),
            (details.width, details.height),
            (0, details.height),
            (-bump, 3*details.height//4),
            (-bump, details.height//4),
            (0,0)]]

class Box(Note):
    style_items = {'offset': '10'}
    @classmethod
    def getPoints(cls, details):
        offset = int(cls.getStyle('offset', details))
        return [(details.x + a, details.y + b) for a, b in [
            (0, 0),
            (details.width, 0),
            (details.width, details.height),
            (0, details.height),
            (0, 0),
            (offset, -offset),
            (details.width+offset, -offset),
            (details.width, 0),
            (details.width + offset, -offset),
            (details.width + offset, -offset+details.height),
            (details.width, details.height)
        ]]

class Drum(BasicShape):
    style_items = {'curve_height': '15'}
    @classmethod
    def getPath(cls, details):
        h, w = details.height, details.width
        x1, y1 = details.x, details.y
        x2, y2 = x1+w, y1+h
        ch = int(cls.getStyle('curve_height', details)) * w // 100
        return ' '.join([f'M {x1} {y1}',
                         f'v {h}',
                         f'C {x1} {y2+ch} {x2} {y2+ch} {x2} {y2}',
                         f'v -{h}',
                         f'C {x2} {y1+ch} {x1} {y1+ch} {x1} {y1}',
                         f'C {x1} {y1-ch} {x2} {y1-ch} {x2} {y1}'])

    @classmethod
    def getShape(cls, details):
        return svg.path(d=cls.getPath(details),
                        stroke_width=cls.getStyle('bordersize', details),
                        stroke=cls.getStyle('bordercolor', details),
                        fill=cls.getStyle('blockcolor', details))

    @classmethod
    def updateShape(cls, shape, details):
        shape['d'] = cls.getPath(details)
        stroke_width = cls.getStyle('bordersize', details)
        stroke = cls.getStyle('bordercolor', details)
        fill = cls.getStyle('blockcolor', details)
        shape['style'] = f"fill:{fill}; stroke_width:{stroke_width}; stroke:{stroke}"

class Stickman(Drum):
    style_items = {'proportions': '25 33 66'}
    @classmethod
    def getPath(cls, details):
        proportions = [int(i) for i in cls.getStyle('proportions', details).split()]
        x1 = details.x
        x2 = details.x + details.width//2
        x3 = details.x + details.width
        y1 = details.y
        r = details.height * proportions[0] // 200
        y2 = y1 + proportions[0] * details.height // 100
        y3 = y1 + proportions[1] * details.height // 100
        y4 = y1 + proportions[2] * details.height // 100
        y5 = y1 + details.height
        return f'M {x2-1} {y2} a {r} {r} 0 1 1 1 0 L {x2} {y4} M {x1} {y3} L {x3} {y3} M {x1} {y5} L {x2} {y4} L {x3} {y5}'


class ObliqueRect(Drum):
    style_items = {'step': '10'}
    @classmethod
    def getPath(cls, details):
        step = int(cls.getStyle('step', details))
        return f'M {details.x} {details.y} h {details.width+step} l -{step} {details.height} h -{details.width+step} l {step} -{details.height}'

class Tunnel(Drum):
    style_items = {'curvature': 20}
    @classmethod
    def getPath(cls, details):
        curve = int(cls.getStyle('curvature', details)) * details.height // 100
        return f'M {details.x} {details.y} h {details.width} c {-curve} {details.height//3} {-curve} {2*details.height//3} 0 {details.height} h -{details.width}  c {-curve} -{details.height//3} {-curve} -{2*details.height//3} 0 -{details.height}'

class Document(Drum):
    style_items = {'step': '15'}
    @classmethod
    def getPath(cls, details):
        step = int(cls.getStyle('step', details))
        return f'M {details.x} {details.y} h {details.width} v {details.height} c -{details.width/2} -{step} -{details.width/2} {step} -{details.width} 0 v -{details.height}'

class Tape(Drum):
    style_items = {'step': '15'}
    @classmethod
    def getPath(cls, details):
        step = int(cls.getStyle('step', details))
        return f'M {details.x} {details.y} c {details.width/2} {step} {details.width/2} -{step} {details.width} 0 v {details.height} c -{details.width/2} -{step} -{details.width/2} {step} -{details.width} 0 v -{details.height}'

class TriangleDown(Drum):
    style_items = {}
    @classmethod
    def getPath(cls, details):
        return f'M {details.x} {details.y} h {details.width} l -{details.width//2} {details.height} L {details.x} {details.y}'

class TriangleUp(Drum):
    style_items = {}
    @classmethod
    def getPath(cls, details):
        return f'M {details.x} {details.y+details.height} h {details.width} l -{details.width//2} -{details.height} L {details.x} {details.y+details.height}'

class Hourglass(Drum):
    style_items = {}
    @classmethod
    def getPath(cls, details):
        return f'M {details.x} {details.y} h {details.width} l -{details.width} {details.height} h {details.width} l -{details.width} -{details.height}'
