""" Tool for processing XML files. This tool handles the following constructs:
        - Removing XML comments from the file
        - Including files using the <include file="name" /> directive
        - Defining new XML tags that are handled as templates: when occuring, the
          newly defined templates are replaced by the XML defined in the template.
        - Within a template, the options and arguments that are supplied to the templated
          tag are expanded using the Mako templating engine.

    The tool writes the generated XML to stdout, allowing the generated XML to be used by other
    tools for various purposes.
"""
import sys
import io
import re
from mako.template import Template
from mako import exceptions


TAG_CLOSE_MSG = '__TAG_CLOSE__'


data_models = {}


def handle_Datamodel(args, lines):
    """ Analyse and store data model definitions """
    name = args['name']
    data_models[name] = {}
    data_model = data_models[name]
    line_it = iter(lines.splitlines())
    l = next(line_it)
    try:
        while True:
            # Consume lines until we get a table
            while not l.strip().startswith('table:'):
                l = next(line_it)

            tablename = l.strip().split(':')[1]
            tabledef = {}
            data_model[tablename.strip()] = tabledef
            # Consume and handle the column definitions
            l = next(line_it)
            while l[0] in ' \t':
                name, details = l.split(':')
                colname = name.strip()
                details = [d.strip() for d in details.split(',')]
                tabledef[colname] = details
                l = next(line_it)
    except StopIteration:
        pass
    return ''


argument_re = re.compile(r'\s*(\S*)\s*=\s*"([^"]*)"')



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
            return handle_Template(arguments, '\n'.join(lines)), parts[-1]
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
    wrapped_tags = '|'.join(r'(%s)(?=[ />])' % t for t in tags)
    tag_start = re.compile(r'<(%s)' % wrapped_tags)
    print ('Searching for tags', wrapped_tags, file=sys.stderr)


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
                template.render(lines=lines, datamodels=data_models, **arguments))
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


generators = {'Datamodel': Tag('Datamodel', handle_Datamodel),
              'Template': template_reader}

update_res(generators)

def processor(generators=generators, istream=sys.stdin, ostream=sys.stdout, preprocess_only=False):
    """ Parses the server definition file.

        Scans the file for XML tags that we handle, and
        executes the associated actions.
    """
    istream = open(istream) if isinstance(istream, str) else istream

    update_res(generators)

    print('Handling tags:', generators.keys(), file=sys.stderr)

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
    import os
    if False:
        os.chdir('/home/ehwaal/projects/sab/admingen/projects/xml_server')
        result = processor(istream=open('test.xml'))
    else:
        os.chdir('/home/ehwaal/projects/sab')
        result = processor(istream=open('webinterface.xml'))
    if result:
        sys.exit(result)
