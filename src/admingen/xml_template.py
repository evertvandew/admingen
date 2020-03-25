""" Tool for processing XML files. This tool handles the following constructs:
        - Removing XML comments from the file
        - Including files using the <include file="name" /> directive
        - Defining new XML tags that are handled as templates: when occuring, the
          newly defined templates are replaced by the XML defined in the template.
        - Within a template, the options and arguments that are supplied to the templated
          tag are expanded using the Mako templating engine.

    The tool writes the generated XML to stdout, allowing the generated XML to be used by other
    tools for various purposes.
    
    We use the Mako templating engine for its powerful inline-Python features. Also its
    syntax does not bite Angular or other popular Javascript libraries.
"""
import sys
import io
import re
import enum
from dataclasses import dataclass
from typing import List, Tuple, Any, Dict
import urllib.parse
from mako.template import Template
from mako import exceptions


TAG_CLOSE_MSG = '__TAG_CLOSE__'


data_models = {}
url_prefixes = {}

def handle_Datamodel(args, lines):
    """ Analyse and store data model definitions """
    def handle_table(line_it):
        """ Read the """
        result = {}
        # Consume and handle the column definitions
        l = next(line_it)
        try:
            while l[0] in ' \t':
                name, details = l.split(':')
                colname = name.strip()
                details = [d.strip() for d in details.split(',')]
                result[colname] = details
                l = next(line_it)
        except StopIteration:
            pass    # Use the exception only to break out of the while loop.
        return l, result
    
    def handle_enum(line_it, table_name):
        """ Currently, al items are numbered from 1 up.
        """
        items = []
        # Every indented line is one item for the enum.
        l = next(line_it)
        try:
            while l and l[0] in ' \t':
                item = l.strip()
                items.append(item)
                l = next(line_it)
        except StopIteration:
            pass    # Use the exception only to break out of the while loop
        return l, enum.Enum(table_name, ' '.join(items))
        
    name = args['name']
    url_prefix = args.get('url_prefix', name)
    data_models[name] = {}
    data_model = data_models[name]
    url_prefixes[url_prefix] = name
    line_it = iter(lines.splitlines())
    l = next(line_it)
    try:
        while True:
            # Consume lines until we get a table or enum
            while l.split(':')[0] not in ['table', 'enum']:
                l = next(line_it)
            
            table_type, tablename = l.strip().split(':', maxsplit=1)
            tablename = tablename.strip()
            tabledef = None
            if table_type.strip() == 'table':
                l, tabledef = handle_table(line_it)
            elif table_type.strip() == 'enum':
                l, tabledef = handle_enum(line_it, tablename)
            data_model[tablename] = tabledef
    except StopIteration:
        pass
    return ''

def isEnum(source, coltype):
    """ Check if a type refers to an enum in the datamodel
    """
    if not coltype:
        return False
    if coltype not in data_models[source]:
        return False
    return isinstance(data_models[source][coltype], enum.EnumMeta)


argument_re = re.compile(r'\s*(\S*)\s*=\s*"([^"]*)"')


@dataclass
class QueryDetails:
    url: str
    source: str=None
    table: str=None
    column_names: List[str]=None
    column_types: List[str]=None
    join = None
    join_on: str=None
    filter: str=None
    group_by: str=None
    order_by: str=None
    parameters: List[str] = None
    

def GetQueryDetails(query, columns):
    """ Pre-parse a query string, as used in the template system.
    The query contains a lot of information that
    needs to be processed to be able to draw the table.
    This script will set some variables that can be inserted at the right locations.
    
    The query string has the following structure:
    """
    if query[0] == '/':
        # First determine which columns to draw
        path = urllib.parse.urlparse(query).path
        table = path.split('/')[-1]
        if (path[0] or path[1]) in url_prefixes:
            source = url_prefixes[path[0] or path[1]]
            specs = data_models[source][table]
        else:
            # This is an unknown data source. Only process parameters
            source = specs = None
    else:
        # The source and table are specified directly
        data_ref, query_part = query.split('?', maxsplit=1)
        assert data_ref.count('.') == 1
        source, table = data_ref.split('.')
        specs = data_models[source][table]
        query = f'/data/{table}?{query_part}'

    # Determine the context that needs to be obtained in JS
    # These elements have double brackets in the query string.
    bit_scanner = re.compile(r'\{\{[^}]*\}\}')
    context_bits = bit_scanner.findall(query)
    context_bits = [b.strip('{}') for b in context_bits]

    # Determine the actual query string, in JS
    parts = bit_scanner.split(query)
    the_query = ''.join([f'"{a}"+context.{b}+' for a, b in zip(parts, context_bits)]) + '"'+parts[-1]+'"'
    details = QueryDetails(source=source, table=table, url=the_query, parameters=context_bits)
    
    if columns:
        details.column_names = columns.split('.')
    elif specs:
        details.column_names = specs.keys()
        print('Column names:', details.column_names)
    return details


def GetQueryContextSetter(details):
    parts = []
    for bit in details.parameters:
        parts.append(f"""            {bit}: $("#{bit}").val()""")
    lines = ['var context = {',
             ',\n'.join(parts),
            '};']
    context_setter = '\n'.join(lines)
    return context_setter

    

def read_argument_lines(line, istream):
    """ Read a stream until all arguments in a Tag are read
        Returns a tuple with 1. the lines inside the tag declaration, 2. the
        terminator, 3. the remainder of the last line outside the declaration.
    """
    lines = []
    while True:
        # Check if the TAG definition is ended
        m = argsend.match(line)
        if m:
            # Add the final bit to the lines with arguments
            ending = m.groups()[-1]
            before = line[:m.span()[1]-len(ending)]
            after = line[m.span()[1]:]
            lines.append(before)
            return lines, ending, after

        lines.append(line)
        line = next(istream)

    

def argument_parser(line, istream):
    """ Read a stream until all arguments in a TAG are read
    :param line: Remained of the first line
    :param istream: File for reading more lines
    :return: <argdict>, is_closed, remained of line
    """
    arg_lines, ending, after = read_argument_lines(line, istream)
    # Join the lines together and parse them to a dictionary
    all_lines = ''.join(arg_lines)
    all_lines.replace('\n', '')
    arguments = {k:v for k, v in argument_re.findall(all_lines)}
    # Return to the one who wants the arguments
    return arguments, (ending == '/>'), after
    

def Tag(tag, handler):
    """ Create a function that will read and handle a specific tag, recursively. """
    start_matcher = re.compile(r'<\s*%s(?=[ />])'%tag)
    end_matcher = re.compile(r'</\s*%s\s*>'%tag)

    def tag_line_reader(line, istream):
        """ Collect all lines (if any) that are, send them through the handler,
            then yield them.
            Always a tuple is yielded. element 1 is what the handler returned,
            and element 2 is what was on the line after the close of the tag.
        """
        # Read the arguments for this tag
        arguments, is_closed, line = argument_parser(line, istream)
        
        if is_closed:
            return handler(arguments, ''), line
        
        lines = []
        while True:
            # Read the lines within the tag (the body)
            
            # Check for new tags that needs handling
            while len(parts := tag_start.split(line, maxsplit=1)) > 1:
                # We found a new tag. Read and handle it.
                before, tagname, after = parts[0], parts[3] or parts[2] or parts[1], parts[-1]
                lines.append(before)
                if tag == 'Template':
                    output, line = generators[tagname](after, istream, False)
                else:
                    output, line = generators[tagname](after, istream)
                lines.append(output)
            
            # No more new tags on the current line
            # Check if the tag is ended.
            if line and len(parts:=end_matcher.split(line)) > 1:
                before, after = parts
                lines.append(before)
                try:
                    return handler(arguments, ''.join(lines)), after
                except:
                    print("An error occured when handling tag in", handler.__name__,
                          "with arguments", arguments,
                          "\nand lines",lines, file=sys.stderr)
                    raise
            else:
                lines.append(line)
                try:
                    line = next(istream)
                except StopIteration:
                    print('Tag not closed:', tag, file=sys.stderr)
                    sys.exit(1)
    
    return tag_line_reader

def template_reader(line, istream):
    """ Read lines from the stream until the closing mark of the current tag is found.
        Then use the lines read to form a new tag: a template tag.
    :param line: Remainder of the tag definition after <tagname
    :param istream: stream containing the lines
    :return: The text enveloped in the tag, including start and end. Also the remainder
             of the line where the tag was closed.
    """
    # Re-add the tag start to the line
    arguments, is_closed, line = argument_parser(line, istream)
    assert not is_closed   # It makes no sense to have a self-closed Template...

    # Eat all lines until the end *without* entering those tags
    lines = []
    while True:
        parts = template_end.split(line)
        if len(parts) > 1:
            lines.append(parts[0])
            return handle_Template(arguments, ''.join(lines)), parts[-1]
        lines.append(line)
        line = next(istream)


def root_line_reader(istream, ostream):
    """ Simple reader for the outer level of the file (root) """
    for line in istream:
        # If there is a new tag in the line, this split action yields three bits:
        # The bit before the tag, the tag name, and the xxxx
        while len(parts := tag_start.split(line, maxsplit=1)) > 1:
            # We found a new tag. Read and handle it.
            before, tagname, after = parts[0], parts[3] or parts[2] or parts[1], parts[-1]
            ostream.write(before)
            tagname = tagname.strip()
            output, line = generators[tagname](after, istream)
            ostream.write(output)

        # Write the remainder to the output file
        ostream.write(line)


def filterComment(instream, outstream):
    line = ''
    while True:
        if not line:
            line = instream.readline()
            if not line:
                return
        parts = line.split('<!--', maxsplit=1)
        if len(parts) > 1:
            outstream.write(parts[0])
        else:
            # No comments in the line: just yield it and continue to the next line
            outstream.write(line)
            line = instream.readline()
            continue

        # There was a comment. Now check if the comment ends in the same line, or another one.
        line = parts[1]
        while line:
            parts = line.split('-->', maxsplit=1)
            if len(parts) > 1:
                # Got the end of the comment. Continue parsing the bit after it.
                line = parts[1]
                break
            # No comment end. Eat a new line.
            line = instream.readline()


def preProcessor(instream, outstream):
    """ Parse the input file, remove comments, and replace any instances of the
       <include file="name" /> tag with the contents of that file.
       Files are included by recursively calling the preprocessor on the included file.
    """
    include_tag = re.compile(r'<include\s*file="(.+?)"\s*/>')
    tmp_file = io.StringIO()
    filterComment(instream, tmp_file)
    tmp_file.seek(0)            # Go back to the beginning of the file
    
    for line in tmp_file:
        # Yeah, py 3.8 has the walrus operator!
        if m:=include_tag.match(line):
            # Found an include directive. Execute it, writing to the output stream.
            file = m.groups()[0]
            preProcessor(open(file), outstream)
        else:
            outstream.write(line)
    
    
tag_start = None
# XML tags can have two endings: "/>" or ">".
argsend = re.compile(r'([^"/>]|("[^"]*?"))*(/?>)')
template_end = re.compile(r'</\s*Template\s*>')


def update_res(generators):
    global tag_start, tag_end
    # We need to ensure long tags are matched before short tags,
    # to prevent 'PageContextValue' to be matched to 'Page'.
    # The simplest way is to reverse-sort the tags.
    tags = sorted(generators.keys(), reverse=True)
    # Prepare a RE to find all custom tags
    # We use the tag name and a lookahead check for a space or tag end character
    wrapped_tags = '|'.join(r'(%s)(?=[\s/>])' % t for t in tags)
    tag_start = re.compile(r'<(%s)' % wrapped_tags)


def handle_Template(args, lines):
    tag = args['tag']
    kwargsdef = {}
    for adef in args.get('args', '').split(','):
        parts = adef.split('=', maxsplit=1)
        if len(parts) > 1:
            kwargsdef[parts[0]] = eval(parts[1])
        else:
            kwargsdef[parts[0]] = ''
    # template = env.from_string(lines)
    template = Template(lines)

    def expand_template(args, lines):
        arguments = kwargsdef.copy()
        for k, v in args.items():
            arguments[k] = v
        if 'id' not in arguments:
            # 'id' is much used in HTML. Ensure it exists.
            arguments['id'] = None
        try:
            expand_self = io.StringIO(
                template.render(lines=lines,
                                datamodels=data_models,
                                isEnum=isEnum,
                                GetQueryDetails=GetQueryDetails,
                                GetQueryContextSetter=GetQueryContextSetter,
                                **arguments))
        except:
            print(exceptions.text_error_template().render(), file=sys.stderr)
            return '<An error occurred when rendering template for %s'%tag
        expand_others = io.StringIO()
        processor(istream=expand_self, ostream=expand_others)
        return expand_others.getvalue()
    # End of expand_template

    generators[tag] = Tag(tag, expand_template)
    update_res(generators)
    return ''
# End of handle_template


default_generators = {'Datamodel': Tag('Datamodel', handle_Datamodel),
              'Template': template_reader}

generators = default_generators.copy()

def processor(ingenerators=generators, istream=sys.stdin, ostream=sys.stdout, preprocess_only=False):
    """ Parses the server definition file.

        Scans the file for XML tags that we handle, and
        executes the associated actions.
    """
    global generators
    if ingenerators != generators:
        generators = ingenerators
    
    istream = open(istream) if isinstance(istream, str) else istream

    update_res(generators)

    ###########################################################################
    ## PRE-PROCESSING
    
    pre_processed = io.StringIO()
    preProcessor(istream, pre_processed)
    pre_processed.seek(0)        # Make the stream readable
    
    if preprocess_only:
        ostream.write(pre_processed.read())
        return

    ###########################################################################
    ## TEMPLATE EXPANSION
    root_line_reader(pre_processed, ostream)
    return

if __name__ == '__main__':
    # Normally, this file is executed through a different script in the `bin` directory.
    # This is only executed when debugging.
    import os
    os.chdir('/home/ehwaal/projects/sab')
    result = processor(istream=open('webinterface.xml'))
