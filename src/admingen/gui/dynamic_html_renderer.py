

import re
import os, os.path
from dataclasses import dataclass, field, fields, is_dataclass

import markdown
import admingen.gui.specification as sp

###############################################################################
## GUI rendering system for a system with the logic in the Client.


# Now render the pages to a server-side Flask system
def join(lines, separator='\n'):
    if isinstance(lines, str):
        return lines
    return separator.join(lines)


class FlaskClientSide:
    def __init__(self):
        self.files = {}
        self.dependencies = '''<script src="/batic/js/jquery-3.7.0.min.js"></script>
    <link rel="stylesheet" type="text/css" href="/batic/css/bootstrap.min.css" />
    <link rel="stylesheet" type="text/css" href="/batic/css/fontawesome.min.css" />
    <link rel="stylesheet" type="text/css" href="/batic/css/solid.min.css" />
    <link rel="stylesheet" type="text/css" href="/batic/css/stylesheet.css" />
    <link rel="stylesheet" type="text/css" href="/batic/css/select2.min.css" />
    <script src="/batic/js/bootstrap.min.js"></script>
    <script src="/batic/js/select2.min.js"></script>'''

        self.container_stack = []

    def render_text(self, text):
        """ Render a text, replacing font-awesome tags with the proper structures. """
        return re.sub(r'{fa-(.*?)}', r'<i class="fa fa-\1"></i>', text)

    @dataclass
    class Component:
        html: str
        js: str = ''

    def SelectionField(self, widget: sp.SelectionField):
        options = ''.join(
            f'<option value="{v}">{n}</option>' for v, n in zip(widget.option_values, widget.option_names))
        container = self.container_stack[-1] if self.container_stack else None
        return self.Component(
            html=f'<div class="col-9"><select id="{widget.key}" name="{widget.key}" class="form-control" style="width:100%">{options}</select></div>',
            js=f'''
                function get_{widget.key}() {{
                    return $("#{widget.key}").val();
                }}
                function set_{widget.key}(value) {{
                    $("#{widget.key}").val(value).change();
                    $("#{widget.key}").select2({{dropdownParent: $('#{container.getId() if container else ''}')}});
                }}
                function set_options_{widget.key}(options) {{
                    // Remove existing options
                    var {widget.key}_select = $("#{widget.key}")[0];
                    var i, L = {widget.key}_select.options.length - 1;
                    for (i = L; i >= 0; i--) {{
                        {widget.key}_select.remove(i);
                    }}

                    // Add the new options
                    options.forEach( (pair, index) => {{
                            let opt = new Option(pair.name, pair.value);
                            {widget.key}_select.add(opt);
                        }}
                    );
                    $("#{widget.key}").select2({{dropdownParent: $('#{container.getId() if container else ''}')}});
                }}
            '''
        )

    def ForeignRecordSelectionField(self, widget: sp.ForeignRecordSelectionField):
        """ For this one, the options are filled in client-side through a query or something like that.
            The widget declares a 'refresh' function that is called with the data.
        """
        return self.Component(
            html=f'<select id="{widget.key}" name="{widget.key}" class="form-control"></select>',
            js=f'''
    function {widget.key}_refresh(data) {{
        var {widget.key}_select = $("#{widget.key}")[0];
        var i, L = {widget.key}_select.options.length - 1;
        for (i = L; i >= 0; i--) {{
            ${widget.key}_select.remove(i);
        }}
        for (var index in data) {{
            var opt = document.createElement('option');
            opt.appendChild(document.createTextNode(index));
            opt.value = data[index].{widget.value_column};
            var txt = data[index].{widget.name_column};
            opt.textContent = txt;
            {widget.key}_select.appendChild(opt);
        }}
    }}
''')

    def Label(self, widget):
        return self.Component(
            html=f'<label class="col-3 col-form-label for="{widget.for_field}">{widget.text}</label>',
        )

    def InputField(self, widget):
        t = 'text'
        n = 'number'
        js = f'''
                    function get_{widget.key}() {{
                        return $("#{widget.key}").val();
                    }}
                    function set_{widget.key}(value) {{
                        $("#{widget.key}").val(value);
                    }}
        '''
        if widget.datatype == 'hidden':
            return self.Component(
                html=f'<input class="form-control id="{widget.key}" name="{widget.key}" type="hidden"></input>',
                js=js
            )

        intype = {'str': t, 'int': n, 'bool': 'checkbox', 'phone': t, 'order': n,
                  'color': 'color', 'email': t, 'password': 'password', 'url': t, 'path': t,
                  'MyDate': 'date', 'hidden': 'hidden'}[widget.datatype.__name__]
        return self.Component(
            html=f'<div class="col-9"><input class="form-control" id="{widget.key}" name="{widget.key}" type="{intype}"></input></div>',
            js=js
        )

    def Row(self, widget):
        children = self.render(widget.children)
        return self.Component(html=f'<div class="form-group row">{children.html}</div>',
                              js=children.js)

    def Markdown(self, widget):
        return self.Component(html=markdown.markdown(widget.text))

    def Button(self, widget):
        btn_type = widget.type or 'primary'
        return self.Component(
            f'<div id="{widget.key}" class="btn btn-large btn-{btn_type}" onclick="{widget.action}">{self.render_text(widget.text)}</div>')

    def Form(self, widget):
        contents = self.render(widget.children)
        setters = '\n'.join(f'set_{key}(data.{key});' for key in widget.item_names)
        getters = ', '.join(f'{key}: get_{key}()' for key in widget.item_names)
        return self.Component(
            html=f'<div class="container-fluid"><form id="{widget.key}" class="form-horizontal">{contents.html}</form></div>',
            js=f'''{contents.js}
            function set_{widget.key}(data) {{
            {setters}
}}
function get_{widget.key}() {{
    data = {{
        {getters}
    }};
    return data;
}}
'''
        )

    def TableRow(self, widget):
        setters = []
        for name, t in zip(widget.column_names, widget.column_types):
            cell = 'let cell' if len(setters) == 0 else 'cell'
            if sp.is_enum(t):
                options = ''.join(f'''
                    if (data.{name} == {option.value}) {{
                        cell.innerHTML = "{option.name}";
                    }}''' for option in t)
                setters.append(f'''
                    {cell} = row.insertCell(-1);{options}''')
            else:
                setters.append(f'''
                    {cell} = row.insertCell(-1);
                    cell.innerHTML = data.{name}
                ''')
        setters = '\n'.join(setters)

        edit_functions = []
        if widget.on_edit_handler:
            edit_functions.append(f'''
                cell = row.insertCell(-1);
                cell.innerHTML = '<i class="fa fa-pen" />';
                cell.onclick = (ev) => {widget.on_edit_handler};''')
        if widget.on_delete_handler:
            edit_functions.append(f'''
                cell = row.insertCell(-1);
                cell.innerHTML = '<i class="fa fa-trash" />';
                cell.onclick = (ev) => {widget.on_delete_handler};''')
        if widget.on_click_handler:
            edit_functions.append(f'''
                row.onclick = (ev) => {widget.on_click_handler};''')
        edit_functions = ''.join(edit_functions)
        return self.Component(html='',
                              js=f'''
                        function set_{widget.key}(row, data) {{
                            {setters}
                            {edit_functions}
                        }}
                              ''')

    def Table(self, widget):
        # The table is filled after the page is loaded, except for the header which is preset.
        has_header = bool(widget.header)
        header = '<thead><tr>' + ''.join(f'<th>{name}</th>' for name in widget.header) + '</tr></thead>'

        return self.Component(html=f'''
            <table id="{widget.key}" class="table table-hover table-bordered">
            {header}
            </table>
''',
                              js=f'''
            {self.render(widget.row_template).js}

            function set_{widget.key}(data) {{
                    /* Update the list showing the all elements in the resource. */
                    var table = $( "table[id|='{widget.key}']" )[0];
                    var i, L = table.rows.length - 1;
                    // Delete all rows except the first (the header with column names)
                    for(i = L; i >= 1; i--) {{
                       table.deleteRow(i);
                    }}
                    data.forEach(function(line) {{
                        var row = table.insertRow(-1);
                        set_{widget.row_template.key}(row, line);
                    }});
            }}
''')

    def Constant(self, widget):
        constant = '{' + ', '.join(f'{k}: {repr(v)}' for k, v in widget.values.items()) + '}'
        return self.Component(
            html='',
            js=f'''
                function get_{widget.key} () {{
                    return {constant};
                }}
                function retrieve_{widget.key} () {{
                    route('{widget.key}/ready', get_{widget.key}());
                }}
                function set_{widget.key}(data) {{
                    alert("Good luck with that");
                }}
            '''
        )

    def FieldValue(self, widget):
        return self.Component('', f'''
            function get_{widget.key} () {{
                return $("{widget.selector}").val();
            }}
        ''')

    def RESTDataSource(self, widget):
        entity_name = widget.entity if isinstance(widget.entity, str) else widget.entity.__name__
        get_url = f'{widget.base_url}/{entity_name}'
        set_url = f'{widget.base_url}/{entity_name}'
        separator = '?'
        if widget.query:
            get_url += '?' + widget.query
            separator = '&'
        return self.Component(
            html='',
            js=f'''
                var last_REST_request_{widget.key} = null;
                function get_{widget.key} () {{
                    return last_REST_request_{widget.key};
                }}
                function retrieve_{widget.key} (query) {{
                    // Start a query
                    let url= "{get_url}";
                    if (query) {{
                        // Construct a query string from the dictionary 'query'.
                        let q2 = Object.entries(query).map((kv) => kv[0]+'='+kv[1]);
                        let q3 = q2.join('&');

                        url = url + "{separator}" + q3;
                    }}
                    $.get(url, function(data) {{
                        // We got the data, route it through the system.
                        last_REST_request_{widget.key} = data;
                        route("{widget.key}/ready", data);
                    }});
                }}
                function retrieve_record_{widget.key} (index) {{
                    // Start a query
                    $.get("{get_url}/"+index, function(data) {{
                        // We got the data, route it through the system.
                        last_REST_request_{widget.key} = data;
                        route("{widget.key}/ready", data);
                    }});
                }}
                function set_{widget.key}(data, index) {{
                    if (data.hasOwnProperty('id') && (data.id != null || index)) {{
                        let i = index || data.id;
                        $.post("{set_url}/"+i, data).fail(() => route("{widget.key}/error")).done(() => route("{widget.key}/success"));
                    }} else {{
                        $.post("{set_url}", data).fail(route("{widget.key}/error")).done(route("{widget.key}/success"));
                    }}
                }}
                function set_record_{widget.key}(index, data) {{
                    $.post("{set_url}/"+index, data).fail(() => route("{widget.key}/error")).done(() => route("{widget.key}/success"));
                }}
                function delete_{widget.key}(index) {{
                    $.ajax({{
                        url: '{set_url}/'+index,
                        type: 'DELETE',
                        success: function(result) {{
                            route("{widget.key}_delete/success")
                        }},
                        fail: function(result) {{
                            route("{widget.key}_delete/error")
                        }}
                    }});
                }}
            '''
        )

    def renderDataManipulationPreparation(self, manipulator: sp.DataManipulation, context: dict = None):
        """ Evaluating data manipulation is a two-step process. The first step writes data in intermediate
            variables. For example, data that is shared in several structures is stored separately.
            Also ForEach operations are performed here.
        """
        # Source data records are to be stored in separate variables.
        isroot = context is None
        context = dict(sources=set(), parts=list()) if isroot else context

        match manipulator:
            case list(manipulators):
                for man in manipulators:
                    self.renderDataManipulationPreparation(man, context)

            case sp.ObjectMapping(src, _index, _target):
                # The source may need to be stored in a temporary variable
                if isinstance(src, str):
                    context['sources'].add(os.path.dirname(src))
                else:
                    self.renderDataManipulationPreparation(src, context)

            case sp.ObjectUnion(srcs):
                for src in srcs:
                    if isinstance(src, str):
                        context['sources'].add(os.path.dirname(src))
                    else:
                        self.renderDataManipulationPreparation(src, context)

            case dict():
                self.renderDataManipulationPreparation(list(manipulator.values()), context)

            case sp.DataForEach(src, rv, inner):
                if isinstance(src, str):
                    context['sources'].add(src)
                else:
                    self.renderDataManipulationPreparation(src, context)

                # Ensure the running variable is not added to the 'sources', but any other externals are
                self.renderDataManipulationPreparation(inner, context)
                to_remove = []
                for s in context['sources']:
                    if s.split('.')[0] == manipulator.rv:
                        to_remove.append(s)
                for s in to_remove:
                    context['sources'].remove(s)

                # Add the code to implement the for each
                context['parts'].append(
                    f'''let temp_{manipulator.getId()} = {self.renderDataManipulation(manipulator.src)}.map( ({manipulator.rv}) => {{ return {self.renderDataManipulation(manipulator.inner)}; }});''')
            case sp.QueryParameter():
                pass  # Nothing to prepare
            case sp.GlobalVariable() | sp.LocalVariable():
                pass  # Nothing to prepare
            case sp.SubElement():
                self.renderDataManipulationPreparation(manipulator.src)
            case sp.ResourceValue():
                pass
            case sp.JSValue():
                pass
            case str():
                context['sources'].add(os.path.dirname(manipulator) or manipulator)
            case _:
                raise RuntimeError(f"Unsupported data manipulator {manipulator}")

        if isroot:
            # return the javascript to be inserted
            sources = [s for s in context['sources'] if s]
            sources = '\n'.join(f'let {source} = get_{source}();' for source in sources)
            parts = '\n'.join(context['parts'])
            return f'{sources}\n{parts}\n'

    def renderDataManipulation(self, manipulator):
        match manipulator:
            case sp.ObjectMapping(src, index, target):
                """ Return a part of a statement assigning an element in an object """
                if not isinstance(src, str):
                    src = self.renderDataManipulation(src)
                if index is not None:
                    return f'{target}: {src}["{index}"]'
                else:
                    return f'{target}: {src}'
            case sp.ObjectUnion(srcs):
                rendered_srcs = [s if isinstance(s, str) else self.renderDataManipulation(s) for s in srcs]
                return '{' + ','.join(rendered_srcs) + '}'
            case sp.DataForEach():
                # The actual foreach is rendered as a separate variable.
                # The intermediate result was stored in a temporary variable.
                return f'temp_{manipulator.getId()}'
            case sp.QueryParameter():
                return f'get_parameter("{manipulator.name}")'
            case sp.SubElement():
                return f'{self.renderDataManipulation(manipulator.src)}[{manipulator.index}]'
            case list():
                return ', '.join(self.renderDataManipulation(i) for i in manipulator)
            case dict():
                rendered_srcs = {k: (s.replace('/', '.') if isinstance(s, str) else self.renderDataManipulation(s)) for
                                 k, s in manipulator.items()}
                return '{' + ', '.join(f'{k}: {v}' for k, v in rendered_srcs.items()) + '}'
            case str():
                return manipulator
            case sp.GlobalVariable():
                return f'global_context.{manipulator.name}'
            case sp.LocalVariable():
                return f'{manipulator.name}'
            case sp.ResourceValue():
                return f'get_{manipulator.src}()'
            case sp.JSValue():
                return manipulator.js
            case _:
                raise RuntimeError(f"Unsupported data manipulator {manipulator}")

    def EventHandler(self, widget):
        # Determine which events to handle
        event_sources = set(rule.event_source for rule in widget.rules)
        scripts = []
        newline = '\n'
        html = []
        external_scripts = []

        for event_source in event_sources:
            rules = [rule for rule in widget.rules if rule.event_source == event_source]
            preparation = self.renderDataManipulationPreparation([list(rule.data_routing.values()) for rule in rules])
            rule_scripts = [preparation]
            for rule in rules:
                data_set = '\n'.join(
                    f'let {dest} = {self.renderDataManipulation(v)};' for dest, v in rule.data_routing.items())
                if isinstance(rule.action, sp.FunctionCall):
                    arguments = ', '.join(rule.data_routing)
                    rule_scripts.append(f'''{data_set}
                    {rule.action.target_function}({arguments});''')
                elif isinstance(rule.action, sp.ShowMessage):
                    w = rule.action
                    rule_scripts.append(
                        f'''show_message("{w.key}", {w.type.value}, "{w.title}", "{w.message}", {repr(w.buttons)});''')
                elif isinstance(rule.action, sp.StateTransition):
                    arguments = [f'{k}="+{k}+"' for k in rule.data_routing]
                    arguments = '&'.join(arguments)
                    rule_scripts.append(f'''{data_set}
                        location.href = "{rule.action.new_state}?{arguments}";
                    ''')
                elif isinstance(rule.action, sp.StoreGlobal):
                    rule_scripts.append(f"global_context.{rule.action.target} = {rule.action.source};")
                elif isinstance(rule.action, sp.PostRequest):
                    rule_scripts.append(f'''{data_set}
                    $.post({repr(rule.action.url)}, data)
                    .done(function(data) {{
                        {rule.action.success_action or 'route("'+rule.action.key+'/ready")'};
                    }}).fail(function(data) {{
                        {rule.action.fail_action or 'route("'+rule.action.key+'/error")'};
                    }});''')
                elif isinstance(rule.action, sp.SubStateMachine):
                    substate = rule.action
                    self.container_stack.append(substate)
                    body = self.render(substate.elements)
                    html.append(f'''
                    <dialog id="{substate.getId()}" style="width:50%;height:50%">
                    {body.html}
                    </dialog>
''')
                    external_scripts.append(body.js)
                    rule_scripts.append(f'''
                    let theDialog = document.getElementById("{substate.key}Dialog");
                    theDialog.showModal();
                    ''')
                    for ev, ac in substate.transitions.items():
                        if ac == 'close':
                            scripts.append(f'''
                            if (event_source == "{ev}") {{
                                let theDialog = document.getElementById("{substate.key}Dialog");
                                theDialog.close();
                            }}''')
                        else:
                            raise RuntimeError(f"Unknown substate action {ac} for event {ev}")
                    self.container_stack.pop()
                else:
                    raise RuntimeError(f"Unknown event handler action {type(rule.action).__name__}")
            scripts.append(f'''
                if (event_source == "{event_source}") {{
                    {newline.join(rule_scripts)}
                }}
            ''')
        script = f'''
        {newline.join(external_scripts)}
        function route(event_source, index) {{
            console.log(event_source);
            {newline.join(scripts)}
        }}
'''
        return self.Component(html='\n'.join(html), js=script)

    def State(self, widget):
        data_sources = self.render(widget.data_sources)
        components = self.render(widget.elements)
        body = f'''{components.html}
<script>
    {data_sources.js}
    {components.js}
    {self.render(widget.event_handler).js}
</script>'''
        dependencies = self.dependencies
        heading = ''
        body = body
        footer = ''
        title = widget.key
        text = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />
        <title>{title}</title>
    {join(dependencies)}
</head>
<body style="margin-top:0px">
<div id="notification" class="modal" tabindex="-1" role="dialog">
  <div class="modal-dialog" role="document">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">A title</h5>
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
      <div class="modal-body">
        <span id="notification_icon" style="font-size:30pt;width:2em"></span><span id="notification_message">Weet je het zeker?</span>
      </div>
      <div class="modal-footer">
        <button id="ack" type="button" class="btn btn-secondary" data-dismiss="modal">Knopje</button>
      </div>
    </div>
  </div>
</div>
<script>
    var global_context = {{}};

    function show_message(key, type, title, msg, buttons) {{
        let icon = $("#notification_icon")[0];
        icon.className = "";
        icon.classList.add('fa');
        if (type==1) {{
            icon.classList.add('fa-check-circle');
            icon.style.color = "#00B60A";
        }} else if (type==2) {{
            icon.classList.add('fa-info-circle');
            icon.style.color = "#0050B6";
        }} else if (type==3) {{
            icon.classList.add('fa-question-circle');
            icon.style.color = "#0050B6";
        }} else if (type==4) {{
            icon.classList.add('fa-exclamation-circle');
            icon.style.color = "#ffa500";
        }} else if (type==5) {{
            icon.classList.add('fa-exclamation-circle');
            icon.style.color = "#ff0000";
        }}
        $("#notification_message")[0].innerHTML = msg;
        $("#notification .modal-title")[0].innerHTML = title;
        buttons_txt = ''
        buttons.forEach(function(txt) {{
            buttons_txt += '<button type="button" class="btn btn-secondary" data-dismiss="modal" onclick="route('+"'"+key+'/'+txt+"'"+')">'+txt+'</button>';
        }});
        $("div[id='notification']  .modal-footer")[0].innerHTML = buttons_txt;
        $("div[id='notification']").modal('show');
    }}
    function show_error(msg) {{
        let icon = $("i[id='notification_icon']")[0];
        icon.className = "";
        icon.classList.add('fa');
        icon.classList.add('fa-exclamation-circle');
        icon.style.color = "#D73A2B";
        $("#notification_message")[0].innerHTML = msg;
        $("div[id='notification']").modal('show');
        $("#notification").find(".modal-title")[0].innerHTML = "Foutmelding";
    }}
    function getCookie(name) {{
        var nameEQ = name + "=";
        var ca = document.cookie.split(';');
        for(var i=0;i < ca.length;i++) {{
            var c = ca[i];
            while (c.charAt(0)==' ') c = c.substring(1,c.length);
            if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
        }}
        return null;
    }}
    function acm_authorized(roles) {{
        var role = getCookie("role_name");
        var allowed_roles = roles.split(',');
        return allowed_roles.includes(role);
    }}

    function now() {{
        var today = new Date();
        var dd = String(today.getDate()).padStart(2, '0');
        var mm = String(today.getMonth() + 1).padStart(2, '0'); //January is 0!
        var yyyy = today.getFullYear();
        var hh = String(today.getHours()).padStart(2, '0');
        var m = String(today.getMinutes()).padStart(2, '0');
        today = dd + '-' + mm + '-' + yyyy + ' ' + hh + ':' + m + ':00';
        return today;
    }}
    function get_parameter(param) {{
        const urlParams = new URLSearchParams(window.location.search);
        const myParam = urlParams.get(param);
        return myParam;
    }}
    $(document).ready(function(){{
        $.ajaxSetup({{
            cache: false,
        }});

        $("#div_current_user").each(function(i){{
            this.innerHTML = getCookie("user_name");
        }});

        // Insert the first event to load data etc.
        route('Document/ready');
    }});

</script>
{join(heading)}
{join(body)}
{join(footer)}
</body>
</html>
'''
        self.files[widget.key] = text
        return self.Component(html=text)

    def render(self, widgets):
        if widgets is None:
            return self.Component(html='')
        if isinstance(widgets, list):
            components = [getattr(self, type(w).__name__)(w) for w in widgets]
            return self.Component(html='\n'.join(c.html for c in components),
                                  js='\n'.join(c.js for c in components))
        return getattr(self, type(widgets).__name__)(widgets)
