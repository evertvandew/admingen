

from typing import Self, Callable, List, Any, Dict, _GenericAlias, Tuple
from dataclasses import dataclass, field, fields, is_dataclass
from enum import EnumMeta, Enum

# Base classes
@dataclass
class DataSource:
    url: str
    model: Any

@dataclass
class Widget:
    key: str

# Structural widgets
@dataclass
class Row:
    children: List[Widget]

@dataclass
class Collapsible:
    heading: str
    children: List[Widget]

# Graphical of a page
@dataclass
class Button(Widget):
    text: str
    action: str
    type: str = ''

@dataclass
class Markdown:
    text: str

# Widgets for building edit forms
@dataclass
class Label(Widget):
    text: str
    for_field: str

@dataclass
class SelectionField(Widget):
    option_names: List[str]
    option_values: List[str | int]

@dataclass
class ForeignRecordSelectionField(Widget):
    datasource: DataSource
    name_column: str = 'naam'
    value_column: str = 'id'

@dataclass
class InputField(Widget):
    datatype: Any

@dataclass
class Form(Widget):
    item_names: List[str]
    item_types: List[Any]
    children: List[Widget]
    submitter: DataSource = None

# Widgets for building tables
@dataclass
class TableRow(Widget):
    column_names: List[str]
    column_types: List[Any]
    on_click_handler: Callable | None = None
    on_edit_handler: Callable | None = None
    on_delete_handler: Callable | None = None

@dataclass
class Table(Widget):
    header: List[str] | None
    row_template: TableRow


###############################################################################
## Data sources

@dataclass
class StateArgument:
    name: str
    type: Any

@dataclass
class RESTDataSource(Widget):
    base_url: str
    entity: str
    query: str = ''

@dataclass
class Constant(Widget):
    values: Dict[str, Any]
    event: str

@dataclass
class FieldValue:
    key: str
    selector: str

###############################################################################
## Routing elements

message_types = Enum('message_types', 'Success Info Question Warning Error')


class DataManipulation:
    def getId(self):
        return hash(id(self))
    def __hash__(self):
        return id(self)

@dataclass
class GlobalVariable:
    name: str

@dataclass
class LocalVariable:
    name: str

@dataclass
class StoreGlobal:
    target: str
    source: str

@dataclass
class QueryParameter:
    name: str

@dataclass
class ObjectMapping(DataManipulation):
    src: str | DataManipulation
    index: str | int | None
    target: str
    def __hash__(self):
        return id(self)

@dataclass
class ObjectUnion(DataManipulation):
    srcs: List[str | DataManipulation]
    def __hash__(self):
        return id(self)

@dataclass
class DataForEach(DataManipulation):
    """ Used to re-organise a data structure. Takes a list, does some manipulations
       and returns a new list. Uses the `map` function, not the `forEach`.
    """
    src: str | DataManipulation
    rv: str                     # Running Variable
    inner: dict | DataManipulation
    def __hash__(self):
        return id(self)

@dataclass
class SubElement(DataManipulation):
    src: str | DataManipulation
    index: int

@dataclass
class ResourceValue(DataManipulation):
    src: str


class Action:
    pass


@dataclass
class ShowMessage(Action):
    key: str
    type: message_types
    title: str
    message: str            # Using the Markdown notation
    buttons: List[str]      # The button text is reused in the generated event when clicked

@dataclass
class FunctionCall(Action):
    target_function: str

@dataclass
class StateTransition(Action):
    new_state: str
    data_routing: Dict[str, DataManipulation] = field(default_factory=dict)

@dataclass
class SubStateMachine(Action):
    key: str
    elements: List[Widget]
    transitions: Dict[str, str]

    def getId(self):
        return self.key+'Dialog'

@dataclass
class PostRequest(Action):
    key: str
    url: str
    success_action: str = ''
    fail_action: str = ''

@dataclass
class EventTrigger(Action):
    event: str

@dataclass
class EventRule:
    event_source: str
    action: FunctionCall | StateTransition | EventTrigger | ShowMessage | SubStateMachine | PostRequest
    data_routing: Dict[str, DataManipulation] = field(default_factory=dict)

@dataclass
class EventHandler:
    rules: List[EventRule]

@dataclass
class State(Widget):
    elements: List[Widget]
    data_sources: Dict[str, DataSource]
    event_handler: EventHandler
    return_url: str = ''


def is_enum(datatype):
    return isinstance(datatype, EnumMeta) or getattr(datatype, '__is_enum__', False)
