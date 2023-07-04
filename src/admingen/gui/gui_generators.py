from typing import Self, Callable, List, Any, Dict, _GenericAlias, Tuple
from dataclasses import dataclass, field, fields, is_dataclass
from enum import EnumMeta, Enum

import specification as sp


###############################################################################
## GUI auto-generation functions

def is_enum(datatype):
    return isinstance(datatype, EnumMeta) or getattr(datatype, '__is_enum__', False)


def getEditWidgets(key, name, datatype):
    if isinstance(datatype, _GenericAlias):
        match datatype._name:
            case 'List':
                print('LIST')
            case 'Dict':
                print('DICT')
    elif is_enum(datatype):
        names = [v.name for v in datatype]
        values = [v.value for v in datatype]
        return [sp.Label(key=f'{key}_label', text=name, for_field=key),
                sp.SelectionField(key=key, option_names=names, option_values=values)
                ]
    elif is_dataclass(datatype):
        # Assume this is a foreign key, to be set by selection.
        return [sp.Label(key=f'{key}_label', text=name, for_field=key),
                sp.SelectionField(key=key, option_names=[], option_values=[])
                ]
    elif datatype == int and key == 'id':
        return [sp.InputField(key=key, datatype='hidden')
                ]
    elif datatype.__name__ in ['int', 'str', 'MyDate', 'date', 'time', 'datetime', 'color', 'password', 'email', 'phone', 'url', 'path']:
        return [sp.Label(key=f'{key}_label', text=name, for_field=key),
                sp.InputField(key=key, datatype=datatype)
                ]
    else:
        raise RuntimeError("Unknown type")

def getSubmittedType(datatype):
    if isinstance(datatype, _GenericAlias):
        match datatype._name:
            case 'List':
                print('LIST')
            case 'Dict':
                print('DICT')
    elif isinstance(datatype, EnumMeta):
        names = [v.name for v in datatype]
        values = [v.value for v in datatype]
        return type(values[0])
    elif is_dataclass(datatype):
        # Assume this is a foreign key, to be set by selection.
        return int
    else:
        return datatype

def getForeignDataSourcesRules(foreign_references, base_url):
    remote_types = set(e.type for e in foreign_references)
    remote_data_sources = [sp.RESTDataSource(f'{t.__name__}_data', base_url, t, '') for t in list(remote_types)]
    text_fields = {t: [f.name for f in fields(t) if f.name != 'id'][0] for t in list(remote_types)}

    rules = []
    # Add the rules for loading the data of these tables
    for src in remote_data_sources:
        rules.append(
            sp.EventRule(
                event_source=f'Document/ready',
                action=sp.FunctionCall(target_function=f'retrieve_{src.key}'),
                data_routing={}
            )
        )

    # Add the rules for handling the new data, adding the options for the selection dropouts
    for ref in foreign_references:
        rules.append(
            sp.EventRule(
                event_source=f'{ref.type.__name__}_data/ready',
                action=sp.FunctionCall(f'set_options_{ref.name}'),
                data_routing={'options': sp.DataForEach(
                    src=f'{ref.type.__name__}_data',
                    rv='rec',
                    inner={'value': 'rec.id', 'name': f'rec.{text_fields[ref.type]}'}
                )}
            )
        )

    return remote_data_sources, rules



def generateEditForm(data_table, data_source, translation_table):
    elements = [dt for dt in fields(data_table) if dt not in fields(sp.Widget)]

    # First create the editor
    my_key = f'{data_table.__name__}Edit'
    keys = [e.name for e in elements]   # For displaying
    all_keys = [e.name for e in fields(data_table)]   # For moving data
    names = [translation_table(n) for n in keys]
    types = [e.type for e in elements]
    children = [sp.Row(children=getEditWidgets(key, name, et)) for key, name, et in zip(keys, names, types)]
    children.append(sp.Row(children=[
        sp.Button(key=f'{my_key}_cancel', text='Cancel {fa-times}', action=f"route('{my_key}/cancel')"),
        sp.Button(key=f'{my_key}_save', text='Save {fa-save}', action=f"route('{my_key}/save')"),
        sp.Button(key=f'{my_key}_delete', text='Verwijderen {fa-trash-alt}', action=f"route('{my_key}/delete')")
    ]))
    children.insert(0, sp.Markdown(text=f'# {data_table.__name__.capitalize()} aanpassen'))
    foreign_selections = [e for e in elements if is_dataclass(e.type)]

    sources, rules = getForeignDataSourcesRules(foreign_selections, data_source.base_url)

    submitted_types = [getSubmittedType(t) for t in types]
    contents = sp.Form(key=f'{my_key}',
            item_names=keys,
            item_types=submitted_types,
            submitter=None,                     # RestApi(url=data_url, model=data_table),
            children=children + sources)
    eh = sp.EventHandler(
        rules=[# Loading the record as the document is loaded
               sp.EventRule(event_source=f'Document/ready',
                         action=sp.FunctionCall(target_function=f'retrieve_record_{data_source.key}'),
                         data_routing={'index': sp.QueryParameter('id')}),
               sp.EventRule(event_source=f'{data_source.key}/ready',
                         action=sp.FunctionCall(target_function=f'set_{my_key}'),
                         data_routing={'data': sp.ResourceValue('Record')}),

               # The Save changes dialog
               sp.EventRule(event_source=f'{my_key}/save',
                         action=sp.FunctionCall(target_function=f'set_record_{data_source.key}'),
                         data_routing={'index': sp.QueryParameter('id'), 'data': {k: f'{my_key}/{k}' for k in all_keys}}),
               sp.EventRule(event_source=f'{data_source.key}/success',
                         action=sp.StateTransition('index.html'),
                         data_routing={}),
               sp.EventRule(event_source=f'{data_source.key}/error',
                         action=sp.ShowMessage(
                             key='save_failure',
                             type=sp.message_types.Error,
                             title="Probleem",
                             message="De gegevens konden niet gewijzigd worden.",
                             buttons=['OK']
                         ),
                         data_routing={}),
               sp.EventRule(event_source=f'save_failure/OK',
                         action=sp.StateTransition('index.html'),
                         data_routing={}),

               # Dialog for canceling edits
               sp.EventRule(event_source=f'{my_key}/cancel',
                         action=sp.StateTransition('index.html'),
                         data_routing={}),

               # The Dialog for deleting the record
               sp.EventRule(event_source=f'{my_key}/delete',
                         action=sp.ShowMessage(
                             key='delete_confirm',
                             type=sp.message_types.Question,
                             title='Verwijderen?',
                             message=f'Wilt u deze {data_table.__name__} verwijderen?',
                             buttons=['OK', 'Cancel']
                         ),
                         data_routing={}),
               sp.EventRule(event_source=f'delete_confirm/OK',
                         action=sp.FunctionCall(target_function=f'delete_{data_source.key}'),
                         data_routing={'index': sp.QueryParameter('id')}),
               sp.EventRule(event_source=f'{data_source.key}_delete/success',
                         action=sp.StateTransition('index.html'),
                         data_routing={}),
               ] + rules
    )
    editor = sp.State(
        key=f'{data_table.__name__}/edit.html',
        elements=contents,
        data_sources=data_source,
        event_handler=eh,
    )
    return editor


def generateAddForm(data_table, data_source, translation_table):
    elements = [dt for dt in fields(data_table) if dt not in fields(sp.Widget) and dt.name != 'id']

    # First create the editor
    my_key = f'{data_table.__name__}Add'
    keys = [e.name for e in elements]
    names = [translation_table(n) for n in keys]
    types = [e.type for e in elements]
    children = [sp.Row(children=getEditWidgets(key, name, et)) for key, name, et in zip(keys, names, types)]
    children.append(sp.Row(children=[
        sp.Button(key=f'{my_key}_cancel', text='Cancel {fa-times}', action=f"route('{my_key}/cancel')"),
        sp.Button(key=f'{my_key}_save', text='Save {fa-save}', action=f"route('{my_key}/save')")
    ]))
    children.insert(0, sp.Markdown(text=f'# {data_table.__name__.capitalize()} aanpassen'))
    submitted_types = [getSubmittedType(t) for t in types]

    foreign_selections = [e for e in elements if is_dataclass(e.type)]
    sources, rules = getForeignDataSourcesRules(foreign_selections, data_source.base_url)

    contents = sp.Form(key=f'{my_key}',
            item_names=keys,
            item_types=submitted_types,
            submitter=None,                     # RestApi(url=data_url, model=data_table),
            children=children + sources)
    eh = sp.EventHandler(
        rules=[sp.EventRule(event_source=f'{my_key}/save',
                         action=sp.FunctionCall(target_function=f'set_{data_source.key}'),
                         data_routing={'data': {k:f'{my_key}/{k}' for k in keys}}),
               sp.EventRule(event_source=f'{data_source.key}/success',
                         action=sp.ShowMessage(
                             key='save_success',
                             type=sp.message_types.Success,
                             title="Success",
                             message="Succesvol opgeslagen.",
                             buttons=['OK']
                         ),
                         data_routing={}),
               sp.EventRule(event_source=f'{data_source.key}/error',
                         action=sp.ShowMessage(
                             key='save_error',
                             type=sp.message_types.Error,
                             title="Fout opgetreden",
                             message="De gegevens konden niet worden opgeslagen.",
                             buttons=['OK']
                         ),
                         data_routing={}),
               sp.EventRule(event_source='save_success/OK',
                         action=sp.StateTransition('index.html'),
                         data_routing={}),
               ] + rules
    )
    editor = sp.State(
        key=f'{data_table.__name__}/add.html',
        elements=contents,
        data_sources=data_source,
        event_handler=eh,
    )
    return editor


def generateListView(data_table, data_source, translation_table):
    my_key = f'{data_table.__name__}List'
    # Elements to display
    elements = [dt for dt in fields(data_table) if dt not in fields(sp.Widget) and dt.name != 'id']
    # Elements to store in the data
    all_keys = [dt.name for dt in fields(data_table)]
    keys = [e.name for e in elements]
    names = [translation_table(n) for n in keys]
    types = [e.type for e in elements]
    contents = [
        sp.Markdown(text=f'# {data_table.__name__.capitalize()} overzicht'),
        sp.Table(
            key=f'{data_table.__name__}Table',
            header = [n.capitalize() for n in names],
            row_template = sp.TableRow(
                key=f'{data_table.__name__}Row',
                column_names=keys,
                column_types=types,
                on_edit_handler=f"route('{my_key}/edit', data.id)",
                on_delete_handler=f"route('{my_key}/delete', data.id)",
            ),
        ),
        sp.Row(children=[sp.Button(key=f'{my_key}_add', text='Add {fa-plus}', action=f"route('{my_key}/add')")])
    ]
    eh = sp.EventHandler(
        rules=[sp.EventRule(event_source=f'Document/ready',
                         action=sp.FunctionCall(target_function=f'retrieve_{data_source.key}'),
                         data_routing={}),
               sp.EventRule(event_source=f'{data_source.key}/ready',
                         action=sp.FunctionCall(target_function=f'set_{data_table.__name__}Table'),
                         data_routing={'data': sp.DataForEach(src=data_source.key, rv='rec', inner=sp.ObjectUnion(srcs=[sp.ObjectMapping(src='rec', index=k, target=k) for k in all_keys]))}),
               sp.EventRule(event_source=f'{my_key}/add',
                         action=sp.StateTransition(new_state='add.html'),
                         data_routing={}),
               sp.EventRule(event_source=f'{my_key}/edit',
                         action=sp.StateTransition(new_state='edit.html'),
                         data_routing={'id': 'index'}),

               # The Dialog for deleting a record.
               sp.EventRule(event_source=f'{my_key}/delete',
                         action=sp.StoreGlobal('record_to_delete', 'index'),
                         data_routing={}),
               sp.EventRule(event_source=f'{my_key}/delete',
                         action=sp.ShowMessage(
                             key='delete_confirm',
                             type=sp.message_types.Question,
                             title='Verwijderen?',
                             message=f'Wilt u deze {data_table.__name__} verwijderen?',
                             buttons=['OK', 'Cancel']
                         ),
                         data_routing={}),
               sp.EventRule(event_source=f'delete_confirm/OK',
                         action=sp.FunctionCall(target_function=f'delete_{data_source.key}'),
                         data_routing={'index': sp.GlobalVariable('record_to_delete')}),
               sp.EventRule(event_source=f'{data_source.key}_delete/success',
                         action=sp.FunctionCall(target_function=f'retrieve_{data_source.key}'),
                         data_routing={}),
               ],
    )
    return sp.State(key=f'{data_table.__name__}/index.html',
        elements=contents,
        data_sources=data_source,
        event_handler=eh
    )



def generateAutoEditor(data_table, data_source, translation_table):
    """ Generate a viewer, editor and adder for new records. """
    return [generateEditForm(data_table, data_source, translation_table),
            generateAddForm(data_table, data_source, translation_table),
            generateListView(data_table, data_source, translation_table)]
