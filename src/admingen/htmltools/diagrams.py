try:
    from browser import document, alert, svg, console, window
except:
    document = {}
    alert = None
    class svg:
        pass
    svg_elements = ['line', 'circle', 'path', 'rect']
    functions = {k: (lambda self, **kargs: kargs) for k in svg_elements}
    svg.__dict__.update(functions)



from typing import Union, Any, List, Self
from dataclasses import dataclass, field, asdict, is_dataclass
from weakref import ref
import enum
from math import inf
import json
from point import Point
from shapes import (Orientations, Shape, CP, Relationship, getMousePos, RoutingMethod, HIDDEN,
                    VAlign, HAlign, Orientations, renderText, OwnerInterface, Container)
import shapes



resize_role = 'resize_decorator'


class DataclassEncoder(json.JSONEncoder):
    def default(self, o):
        if is_dataclass(o):
            return asdict(o) | {'__dataclass__': type(o).__name__}
        return json.JSONEncoder.default(self, o)

to_update = {
    Orientations.TL: [Orientations.TR, Orientations.BL, Orientations.LEFT, Orientations.RIGHT, Orientations.TOP, Orientations.BOTTOM],
    Orientations.TOP: [Orientations.TL, Orientations.TR, Orientations.LEFT, Orientations.RIGHT, Orientations.TOP],
    Orientations.TR: [Orientations.TL, Orientations.BR, Orientations.LEFT, Orientations.RIGHT, Orientations.TOP, Orientations.BOTTOM],
    Orientations.RIGHT: [Orientations.TR, Orientations.BR, Orientations.RIGHT, Orientations.TOP, Orientations.BOTTOM],
    Orientations.BR: [Orientations.BL, Orientations.TR, Orientations.LEFT, Orientations.RIGHT, Orientations.TOP, Orientations.BOTTOM],
    Orientations.BOTTOM: [Orientations.BL, Orientations.BR, Orientations.LEFT, Orientations.RIGHT, Orientations.BOTTOM],
    Orientations.BL: [Orientations.BR, Orientations.TL, Orientations.LEFT, Orientations.RIGHT, Orientations.TOP, Orientations.BOTTOM],
    Orientations.LEFT: [Orientations.TL, Orientations.BL, Orientations.LEFT, Orientations.TOP, Orientations.BOTTOM],
}
locations = {
    Orientations.TL: lambda x, y, w, h: (x, y + h),
    Orientations.TOP: lambda x, y, w, h: (x + w // 2, y + h),
    Orientations.TR: lambda x, y, w, h: (x + w, y + h),
    Orientations.RIGHT: lambda x, y, w, h: (x + w, y + h // 2),
    Orientations.BR: lambda x, y, w, h: (x + w, y),
    Orientations.BOTTOM: lambda x, y, w, h: (x + w // 2, y),
    Orientations.BL: lambda x, y, w, h: (x, y),
    Orientations.LEFT: lambda x, y, w, h: (x, y + h // 2),
}
orientation_details = {
                Orientations.TL: (1, 0, -1, 1, 1, 1),
                Orientations.TOP: (0, 0, 0, 1, 0, 1),
                Orientations.TR: (0, 0, 1, 1, 1, 1),
                Orientations.RIGHT: (0, 0, 1, 0, 1, 0),
                Orientations.BR: (0, 1, 1, -1, 1, 1),
                Orientations.BOTTOM: (0, 1, 0, -1, 0, 1),
                Orientations.BL: (1, 1, -1, -1, 1, 1),
                Orientations.LEFT: (1, 0, -1, 0, 1, 0)
            }

def moveSingleHandle(decorators, widget, orientation):
    d = decorators[orientation]
    x, y, width, height = [getattr(widget, k) for k in ['x', 'y', 'width', 'height']]
    d['cx'], d['cy'] = locations[orientation](x, y, width, height)

def moveHandles(decorators, widget, orientation):
    # Determine which markers to move
    for o in to_update[orientation]:
        moveSingleHandle(decorators, widget, o)

def moveAll(widget, decorators):
    for o in Orientations:
        moveSingleHandle(decorators, widget, o)

class BehaviourFSM:
    def mouseDownShape(self, diagram, widget, ev):
        pass
    def mouseDownConnection(self, diagram, widget, ev):
        pass
    def mouseDownPort(self, diagram, widget, ev):
        pass
    def mouseDownBackground(self, diagram, ev):
        pass
    def onMouseUp(self, diagram, ev):
        pass
    def onMouseMove(self, diagram, ev):
        pass
    def onKeyDown(self, diagram, ev):
        pass
    def delete(self, diagram):
        """ Called when the FSM is about to be deleted"""
        pass


class ResizeStates(BehaviourFSM):
    States = enum.IntEnum("States", "NONE DECORATED MOVING RESIZING")

    def __init__(self, diagram):
        super(self).__init__(self)
        self.state = self.States.NONE
        self.diagram = diagram
        self.widget = None
        self.decorators = []

    def mouseDownShape(self, diagram, widget, ev):
        if self.state != self.States.NONE and self.widget != widget:
            self.unselect()
        if self.state == self.States.NONE:
            self.select(widget)
        self.state = self.States.MOVING
        self.dragstart = getMousePos(ev)
        self.initial_pos = widget.getPos()
        ev.stopPropagation()
        ev.preventDefault()

    def mouseDownConnection(self, diagram, widget, ev):
        # We need to change the state machine
        if self.state != self.States.NONE:
            self.unselect()
        fsm = RerouteStates(self.diagram)
        self.diagram.changeFSM(fsm)
        fsm.mouseDownConnection(diagram, widget, ev)

    def mouseDownBackground(self, diagram, ev):
        if self.widget and ev.target == self.widget.shape:
            self.state = self.States.MOVING
            return
        if ev.target == diagram.canvas:
            if self.state == self.States.DECORATED:
                self.unselect()
        self.state = self.States.NONE
        return
        self.dragstart = getMousePos(ev)
        if self.widget:
            self.initial_pos = diagram.selection.getPos()
            self.initial_size = diagram.selection.getSize()


    def onMouseUp(self, diagram, ev):
        # If an object was being moved, evaluate if it changed owner
        if self.state == self.States.MOVING:
            pos = getMousePos(ev)
            diagram.evaluateOwnership(self.widget, pos, self.widget.owner)
        if self.state in [self.States.MOVING, self.States.RESIZING]:
            self.state = self.States.DECORATED

    def onMouseMove(self, diagram, ev):
        if self.state in [self.States.NONE, self.States.DECORATED]:
            return
        delta = getMousePos(ev) - self.dragstart
        if self.state == self.States.RESIZING:
            self.onDrag(self.initial_pos, self.initial_size, delta)
        if self.state == self.States.MOVING:
            self.widget.setPos(self.initial_pos + delta)
            diagram.rerouteConnections(self.widget)

    def delete(self, diagram):
        """ Called when the FSM is about to be deleted"""
        if self.state != self.States.NONE:
            self.unselect()

    def startResize(self, widget, orientation, ev):
        self.dragstart = getMousePos(ev)
        self.state = self.States.RESIZING
        self.initial_pos = widget.getPos()
        self.initial_size = widget.getSize()

    def unselect(self):
        for dec in self.decorators.values():
            dec.remove()
        self.decorators = {}
        if self.widget:
            self.widget.unsubscribe(resize_role)
        self.widget = None
        self.state = self.States.NONE

    def select(self, widget):
        self.widget = widget

        self.decorators = {k: svg.circle(r=5, stroke_width=0, fill="#29B6F2") for k in Orientations}
        x, y, width, height = [getattr(widget, k) for k in ['x', 'y', 'width', 'height']]

        for k, d in self.decorators.items():
            d['cx'], d['cy'] = locations[k](x, y, width, height)

        def bind_decorator(d, orientation):
            def dragStart(ev):
                self.dragged_handle = orientation
                self.startResize(widget, orientation, ev)
                ev.stopPropagation()

            d.bind('mousedown', dragStart)

        for orientation, d in self.decorators.items():
            self.diagram.canvas <= d
            bind_decorator(d, orientation)

        widget.subscribe(resize_role, lambda w: moveAll(w, self.decorators))

    def onDrag(self, origin, original_size, delta):
        dx, dy, sx, sy, mx, my = orientation_details[self.dragged_handle]
        d = self.decorators[self.dragged_handle]
        shape = self.widget
        movement = Point(x=delta.x * dx, y=delta.y * dy)
        # alert(f"{delta}, {dx}, {dy}, {sx}, {sy}")
        shape.setPos(origin + movement)
        resizement = Point(x=original_size.x + sx * delta.x, y=original_size.y + sy * delta.y)
        shape.setSize(resizement)

        moveHandles(self.decorators, shape, self.dragged_handle)
        self.diagram.rerouteConnections(shape)

    def onKeyDown(self, diagram, ev):
        if ev.key == 'Delete':
            if self.state != self.States.NONE:
                widget = self.widget
                self.unselect()
                diagram.deleteBlock(widget)


class RerouteStates(BehaviourFSM):
    States = enum.IntEnum('States', 'NONE DECORATED HANDLE_SELECTED POTENTIAL_DRAG DRAGGING')
    def __init__(self, diagram):
        super(self).__init__(self)
        self.state = self.States.NONE
        self.diagram = diagram
        self.decorators = []
        self.dragged_index = None

    def mouseDownShape(self, diagram, widget, ev):
        # We need to change the state machine
        if self.state != self.States.NONE:
            self.clear_decorations()
        fsm = ResizeStates(self.diagram)
        self.diagram.changeFSM(fsm)
        fsm.mouseDownShape(diagram, widget, ev)


    def mouseDownConnection(self, diagram, widget, ev):
        self.widget = widget
        if not self.decorators:
            self.decorate()
        self.state = self.States.POTENTIAL_DRAG
        self.dragstart = getMousePos(ev)
        self.dragged_index = None
        ev.stopPropagation()
        ev.preventDefault()

    def mouseDownBackground(self, diagram, ev):
        if diagram.selection and ev.target == diagram.selection.shape:
            self.state = self.States.MOVING
            return
        if ev.target == diagram.canvas:
            if self.state == self.States.DECORATED:
                self.clear_decorations()
        self.state = self.States.NONE
        return
        self.dragstart = getMousePos(ev)
        if diagram.selection:
            self.initial_pos = diagram.selection.getPos()
            self.initial_size = diagram.selection.getSize()

    def handleDragStart(self, index, ev):
        self.state = self.States.DRAGGING
        ev.stopPropagation()
        ev.preventDefault()

    def dragHandle(self, ev):
        delta = getMousePos(ev) - self.drag_start
        new_pos = self.initial_pos + delta
        handle = self.decorators[self.dragged_index]
        if self.handle_orientation[self.dragged_index] == 'X':
            handle['x1'] = handle['x2'] = new_pos.x
            self.widget.waypoints[self.dragged_index] = Point(x=new_pos.x, y=inf)
        else:
            handle['y1'] = handle['y2'] = new_pos.y
            self.widget.waypoints[self.dragged_index] = Point(x=inf, y=new_pos.y)

    def onMouseUp(self, diagram, ev):
        if self.state in [self.States.POTENTIAL_DRAG, self.States.DRAGGING]:
            self.widget.router.dragEnd(self.diagram.canvas)
            if self.state == self.States.DRAGGING:
                self.state = self.States.HANDLE_SELECTED
            else:
                self.state = self.States.DECORATED

    def onMouseMove(self, diagram, ev):
        if self.state in [self.States.NONE, self.States.DECORATED, self.States.HANDLE_SELECTED]:
            return
        pos = getMousePos(ev)
        if self.state == self.States.POTENTIAL_DRAG:
            delta = pos - self.dragstart
            if len(delta) > 10:
                self.widget.router.createWaypointByDrag(pos, self.widget, self.diagram.canvas)
                self.state = self.States.DRAGGING
        if self.state == self.States.DRAGGING:
            self.widget.router.dragHandle(pos)
            diagram.rerouteConnections(self.widget)

    def onKeyDown(self, diagram, ev):
        if ev.key == 'Delete':
            if self.state == self.States.DECORATED:
                # Delete the connection
                self.clear_decorations()
                self.state = self.States.NONE
                diagram.deleteConnection(self.widget)
            elif self.state != self.States.NONE:
                self.widget.router.deleteWaypoint()
                diagram.rerouteConnections(self.widget)

    def delete(self, diagram):
        if self.state != self.States.NONE:
            self.clear_decorations()

    def decorate(self):
        self.widget.router.decorate(self.widget, self.diagram.canvas)

    def clear_decorations(self):
        self.widget.router.clear_decorations()


class ConnectionEditor(BehaviourFSM):
    States = enum.IntEnum('States', 'NONE A_SELECTED RECONNECTING')
    ConnectionRoles = enum.IntEnum('ConnectionRoles', 'START FINISH')
    def __init__(self, connectionFactory):
        self.connectionFactory = connectionFactory
        self.state = self.States.NONE
        self.a_party = None
        self.connection = None
        self.b_connection_role = None
        self.path = None
    def mouseDownShape(self, diagram, widget, ev):
        party = widget.getConnectionTarget(ev)
        if self.state in [self.States.A_SELECTED, self.States.RECONNECTING]:
            if diagram.allowsConnection(self.a_party, party):
                if self.state == self.States.A_SELECTED:
                    diagram.connect(self.a_party, party, self.connectionFactory)
                elif self.state == self.States.RECONNECTING:
                    match self.b_connection_role:
                        case self.ConnectionRoles.START:
                            self.connection.start = party
                        case self.ConnectionRoles.FINISH:
                            self.connection.start = party
                    diagram.reroute(self.connection)

                self.path.remove()
                self.state = self.States.NONE
        elif self.state == self.States.NONE:
            self.state = self.States.A_SELECTED
            self.a_party = party
            # Create a temporary path to follow the mouse
            x, y = (self.a_party.getPos() + self.a_party.getSize()/2).astuple()
            self.path = svg.line(x1=x, y1=y, x2=x, y2=y, stroke_width=2, stroke="gray")
            diagram.canvas <= self.path
    def onMouseMove(self, diagram, ev):
        if self.state == self.States.NONE:
            return
        pos = getMousePos(ev)
        # Let the temporary line follow the mouse.
        # But ensure it doesn't hide the B-shape
        v = pos - self.a_party.getPos()
        delta = (v/len(v)) * 2
        self.path['x2'], self.path['y2'] = (pos - delta).astuple()
    def delete(self, diagram):
        if self.state != self.States.NONE:
            self.path.remove()
    def onKeyDown(self, diagram, ev):
        if ev.key == 'Escape':
            if self.state == self.States.A_SELECTED:
                # Delete the connection
                self.path.remove()
                self.state = self.States.NONE


class Diagram(OwnerInterface):
    ModifiedEvent = 'modified'
    ConnectionModeEvent = 'ConnectionMode'
    NormalModeEvent = 'NormalMode'

    def __init__(self, widgets):
        self.selection = None
        self.mouse_events_fsm = None
        self.children = []
        self.connections = []
        self.widgets = widgets

    def getCanvas(self):
        return self.canvas

    def onChange(self):
        self.canvas.dispatchEvent(window.CustomEvent.new("modified", {
            "bubbles": True
        }))

    def drop(self, block):
        if self.mouse_events_fsm is not None:
            self.mouse_events_fsm.delete(self)
        block.create(self)
        self.children.append(block)
        self.onChange()

    def deleteConnection(self, connection):
        if connection in self.connections:
            connection.delete()
            self.connections.remove(connection)
            self.onChange()

    def deleteBlock(self, block):
        if owner := block.owner():
            block.delete()
            owner.children.remove(block)

            # Also delete all connections with this block or its ports
            to_remove = []
            ports = getattr(block, 'ports', [])
            for c in self.connections:
                if c.start == block or c.start in ports or c.finish == block or c.finish in ports:
                    to_remove.append(c)
            for c in to_remove:
                self.deleteConnection(c)
            self.onChange()

    def allowsConnection(self, a, b):
        return True

    def connect(self, a, b, cls):
        connection = cls(start=a, finish=b, waypoints=[], routing_method=RoutingMethod.Squared)
        #connection = cls(start=a, finish=b, waypoints=[], routing_method=RoutingMethod.CenterTCenter)
        self.connections.append(connection)
        connection.route(self, self.children)
        self.onChange()

    def changeFSM(self, fsm):
        if self.mouse_events_fsm is not None:
            self.mouse_events_fsm.delete(self)
        self.mouse_events_fsm = fsm

    def getConnectionsToShape(self, widget):
        return [c for c in self.connections if widget.isConnected(c.start) or widget.isConnected(c.finish)]

    def rerouteConnections(self, widget):
        if isinstance(widget, Relationship):
            widget.reroute(self.children)
        else:
            for c in self.getConnectionsToShape(widget):
                c.reroute(self.children)

    def bind(self, canvas):
        self.canvas = canvas
        canvas.bind('click', self.onClick)
        canvas.bind('mouseup', self.onMouseUp)
        canvas.bind('mousemove', self.onMouseMove)
        canvas.bind('mousedown', self.onMouseDown)
        canvas.bind('handle_drag_start', self.handleDragStart)
        canvas.serialize = self.serialize
        document.bind('keydown', self.onKeyDown)
        for widget in self.widgets:
            widget(self)

    def clickChild(self, widget, ev):
        # Check if the ownership of the block has changed
        pos = getMousePos(ev)
        self.takeOwnership(widget, pos, self)


    def mouseDownChild(self, widget, ev):
        if not self.mouse_events_fsm:
            self.mouse_events_fsm = ResizeStates(self)
        self.mouse_events_fsm.mouseDownShape(self, widget, ev)


        # Also notify any listeners that an object was selected
        details = json.dumps(widget, cls=DataclassEncoder)
        self.canvas.dispatchEvent(window.CustomEvent.new("shape_selected", {
            "bubbles":True,
            "detail": {
                "values": details,
                "update": widget.update,
                "object": widget
            }
        }))


    def mouseDownConnection(self, connection, ev):
        if not self.mouse_events_fsm:
            self.mouse_events_fsm = RerouteStates(self)
        self.mouse_events_fsm.mouseDownConnection(self, connection, ev)

    def takeOwnership(self, widget, pos, ex_owner):
        pass

    def onClick(self, ev):
        pass

    def onMouseDown(self, ev):
        self.mouse_events_fsm and self.mouse_events_fsm.mouseDownBackground(self, ev)

    def onMouseUp(self, ev):
        self.mouse_events_fsm and self.mouse_events_fsm.onMouseUp(self, ev)

    def onMouseMove(self, ev):
        self.mouse_events_fsm and self.mouse_events_fsm.onMouseMove(self, ev)

    def onKeyDown(self, ev):
        self.mouse_events_fsm and self.mouse_events_fsm.onKeyDown(self, ev)

    def handleDragStart(self, ev):
        self.mouse_events_fsm and self.mouse_events_fsm.handleDragStart(self, ev)

    def onHover(self):
        pass

    def getMenu(self):
        pass

    def onDrop(self):
        pass

    def serialize(self):
        # Output the model in JSON format
        details = {'blocks': self.children,
                   'connections': self.connections}
        return json.dumps(details, cls=DataclassEncoder)



###############################################################################
## Diagrams and shapes
@dataclass
class Note(Shape):
    description: str = ''
    default_style = dict(blockcolor='#FFFBD6', font='Arial', fontsize='16', textcolor='black', xmargin=2, ymargin=2,
                         halign=HAlign.LEFT, valign=VAlign.CENTER)
    TextWidget = shapes.Text('description')
    def getShape(self):
        # This shape consists of two parts: the text and the outline.
        g = svg.g()
        g <= shapes.Note.getShape(self)
        g <= self.TextWidget.getShape(self)
        return g

    def updateShape(self, shape):
        shapes.Note.updateShape(shape.children[0], self)
        self.TextWidget.updateShape(shape.children[1], self)

@dataclass
class Constraint(Note):
    pass

@dataclass
class Anchor(Relationship):
    source: (Note, Constraint) = None
    dest: Any = None
    name: str = ''


@dataclass
class FlowPort(CP):
    name: str = ''

    def getShape(self):
        p = self.pos
        return svg.rect(x=p.x-5, y=p.y-5, width=10, height=10, stroke_width=1, stroke='black', fill='lightgreen')
    def updateShape(self, shape):
        p = self.pos
        shape['x'], shape['y'], shape['width'], shape['height'] = int(p.x-5), int(p.y-5), 10, 10

    def getPos(self):
        return self.pos
    def getSize(self):
        return Point(1,1)

@dataclass
class FlowPortIn(FlowPort):
    pass

@dataclass
class FlowPortOut(FlowPort):
    pass

@dataclass
class FullPort(FlowPort):
    pass

@dataclass
class Block(Shape):
    description: str = ''
    ports: [FlowPort, FullPort] = field(default_factory=list)
    children: [Self] = field(default_factory=list)

    default_style = dict(font='Arial', fontsize='16', textcolor='black', xmargin=2, ymargin=2, halign=HAlign.CENTER,
                         valign=VAlign.CENTER)
    TextWidget = shapes.Text('name')

    def getPointPosFunc(self, orientation, ports):
        match orientation:
            case Orientations.LEFT:
                return lambda i: Point(x=self.x, y=self.y + self.height / len(ports) / 2 * (2 * i + 1))
            case Orientations.RIGHT:
                return lambda i: Point(x=self.x + self.width,
                                                y=self.y + self.height / len(ports) / 2 * (2 * i + 1))
            case Orientations.TOP:
                return lambda i: Point(x=self.x + self.width / len(ports) / 2 * (2 * i + 1), y=self.y)
            case Orientations.BOTTOM:
                return lambda i: Point(x=self.x + self.width / len(ports) / 2 * (2 * i + 1), y=self.y + self.height)

    def getShape(self):
        g = svg.g()
        # Add the core rectangle
        g <= shapes.Rect.getShape(self)
        # Add the text
        g <= self.TextWidget.getShape(self)
        # Add the ports
        port_shape_lookup = {}      # A lookup for when the port is clicked.
        sorted_ports = {orientation: sorted([p for p in self.ports if p.orientation == orientation], key=lambda x: x.order) \
                       for orientation in Orientations}
        for orientation in [Orientations.LEFT, Orientations.RIGHT, Orientations.BOTTOM, Orientations.TOP]:
            ports = sorted_ports[orientation]
            pos_func = self.getPointPosFunc(orientation, ports)

            for i, p in enumerate(ports):
                p.pos = pos_func(i)
                s = p.getShape()
                g <= s
                port_shape_lookup[s] = p
        self.port_shape_lookup = port_shape_lookup

        # Return the group of objects
        return g

    def updateShape(self, shape):
        # Update the rect
        rect = shape.children[0]
        shapes.Rect.updateShape(rect, self)
        text = shape.children[1]
        self.TextWidget.updateShape(text, self)

        # Update the ports
        sorted_ports = {orientation: sorted([p for p in self.ports if p.orientation == orientation], key=lambda x: x.order) \
                       for orientation in Orientations}

        # Delete any ports no longer used
        deleted = [s for s, p in self.port_shape_lookup.items() if p not in self.ports]
        for s in deleted:
            s.remove()
        shape_lookup = {p.id: s for s, p in self.port_shape_lookup.items()}

        for orientation in [Orientations.LEFT, Orientations.RIGHT, Orientations.BOTTOM, Orientations.TOP]:
            ports = sorted_ports[orientation]
            pos_func = self.getPointPosFunc(orientation, ports)
            for i, p in enumerate(ports):
                p.pos = pos_func(i)
                if p.id in shape_lookup:
                    p.updateShape(shape_lookup[p.id])
                else:
                    s = p.getShape()
                    shape <= s
                    self.port_shape_lookup[s] = p


    def getConnectionTarget(self, ev):
        # Determine if one of the ports was clicked on.
        port = self.port_shape_lookup.get(ev.target, None)
        if port is None:
            return self
        return port

    def isConnected(self, target):
        return (target == self) or target in self.ports

@dataclass
class FullPortConnection(Relationship):
    name: str = ''
    source: (FlowPort, FlowPortOut) = field(default_factory=list)
    Dest: (FlowPort, FlowPortIn) = field(default_factory=list)

class BlockDefinitionDiagram(Diagram):
    allowed_blocks = [Note, Block, shapes.Container]

diagrams = []


def nop(ev):
    return

class BlockCreateWidget:
    height = 40
    margin = 10
    def __init__(self, diagram):
        self.diagram = ref(diagram)
        blocks = diagram.__class__.allowed_blocks
        g = svg.g()
        g <= svg.rect(x=0, width=2*self.margin+1.6*self.height, y=0, height=len(blocks)*(self.height+self.margin)+self.margin,
                      fill='white', stroke='black', stroke_width="2")
        for i, b in enumerate(blocks):
            instance = b(name='', x=self.margin, y=i*(self.height+self.margin)+self.margin,
                         height=self.height, width=1.6*self.height)
            shape = instance.getShape()
            g <= shape
            g <= svg.text(b.__name__, x=self.margin+5, y=i*(self.height+self.margin)+self.margin + self.height/1.5,
                font_size=12, font_family='arial')

            def bindFunc(index, block):
                return lambda ev: self.onMouseDown(ev, index, block)

            shape.bind('mousedown', bindFunc(i, b))
        diagram.canvas <= g

    def onMouseDown(self, ev, index, block):
        diagram = self.diagram()
        if diagram is None:
            return
        # Simply create a new block at the default position.
        instance = block(name='', x=300, y=300, height=self.height, width=int(1.6*self.height))
        diagram.drop(instance)


def createDiagram(canvas_id):
    canvas = document[canvas_id]
    diagram = BlockDefinitionDiagram(widgets=[BlockCreateWidget])
    diagrams.append(diagram)
    diagram.bind(canvas)

    canvas.bind(Diagram.ConnectionModeEvent, lambda ev: diagram.changeFSM(ConnectionEditor(Relationship)))
    canvas.bind(Diagram.NormalModeEvent, lambda ev: diagram.changeFSM(None))


window.createDiagram = createDiagram
