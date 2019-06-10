import sys
import io
import re
from mako.template import Template


TAG_CLOSE_MSG = '__TAG_CLOSE__'




data_models = {}

def handle_Template(args, lines):
    tag = args['tag']
    kwargsdef = {}
    for adef in args.get('args', '').split(','):
        parts = adef.split('=', maxsplit=1)
        if len(parts) > 1:
            kwargsdef[parts[0]] = eval(parts[1])
        else:
            kwargsdef[parts[0]] = ''
    #template = env.from_string(lines)
    template = Template(lines)

    def expand_template(args, lines):
        arguments = kwargsdef.copy()
        for k, v in args.items():
            arguments[k] = v
        return template.render(lines=lines, datamodels=data_models, **arguments)

    generators[tag] = Tag(expand_template)
    update_res()
    return ''


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


def Tag(handler):
    """ Collect all lines (if any) that are, wrap them in the handler,
        then yield them.
    """
    def generator():
        arguments = None
        lines = []
        while True:
            line = yield None

            if isinstance(line, dict):
                arguments = line
                continue

            if line and line[0] == TAG_CLOSE_MSG:
                yield handler(arguments, ''.join(lines))
                return

            lines.append(line)
    return generator



generators = {'Template': Tag(handle_Template),
              'Datamodel': Tag(handle_Datamodel)}



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

argument_re = re.compile(r'\s*(\S*)\s*=\s*"([^"]*)"')

def argument_parser():
    arg_lines = []
    while True:
        line = yield None

        if not line:
            continue

        if line[0] == TAG_CLOSE_MSG:
            all_lines = ''.join(arg_lines)
            all_lines.replace('\n', '')
            arguments = {k:v for k, v in argument_re.findall(all_lines)}
            yield arguments
            return

        arg_lines.append(line)


tag_start = None
tag_end = None
# XML tags can have two endings: "/>" or ">".
argsend = re.compile(r'([^"/>]|("[^"]*?"))*(/?>)')
template_end = re.compile(r'</\s*Template\s*>')


def update_res():
    global tag_start, tag_end
    # Prepare a RE to find all custom tags
    wrapped_tags = '|'.join('(%s)' % t for t in generators.keys())
    tag_start = re.compile(r'<(%s)' % wrapped_tags)
    tag_end = re.compile(r'</(%s)>' % wrapped_tags)





def processor(istream, ostream):
    """ Parses the server definition file.

        Scans the file for XML tags that we handle, and
        executes the associated actions.
    """
    without_comments = io.StringIO()
    filterComment(istream, without_comments)
    # Make the stream readable
    without_comments.seek(0)

    update_res()

    line = ''
    tag_stack = []
    while True:
        if not line:
            line = without_comments.readline()
        if not line:
            return

        # See if a new tag is being started
        parts = tag_start.split(line, maxsplit=1)
        if len(parts) > 1:
            # We found one!
            # Feed the bit before the tag to the current tag / document
            if tag_stack:
                tag_stack[-1].send(parts[0])
            else:
                ostream.write(parts[0])
            # Create the new tag
            new_tag = generators[parts[1]]()
            tag_stack.append(new_tag)
            new_tag.send(None)              # Start the co-routine
            line = parts[-1]

            # Read the arguments to the tag
            ap = argument_parser()
            ap.send(None)
            while True:
                m = argsend.match(line)
                if m:
                    # The arguments are complete. Send the last bit to the parser
                    end = m.groups()[-1]
                    ap.send(line[:m.span()[1]-len(end)])
                    # Retrieve the arguments and send them to the tag
                    args = ap.send((TAG_CLOSE_MSG, ))
                    new_tag.send(args)
                    if end == '/>':
                        # The tag is closed already 8-(
                        result = new_tag.send((TAG_CLOSE_MSG,))
                        tag_stack.pop(-1)
                        if tag_stack:
                            tag_stack[-1].send(result)
                        else:
                            ostream.write(result)

                    # parse the remainder of the line
                    line = line[m.span()[1]:]
                    break

        # If we are dealing with the Template tag, *do not* render inner tags
        if len(parts) > 1 and parts[1] == 'Template':
            # Eat all lines until the end *without* entering those tags
            while True:
                parts = template_end.split(line)
                if len(parts) <= 1:
                    tag_stack[-1].send(line)
                    line = without_comments.readline()
                else:
                    break


        # See if a tag is being closed
        parts = tag_end.split(line, maxsplit=1)
        if len(parts) > 1:
            # We found one!
            # Feed the bit before the closure to the current tag
            tag_stack[-1].send(parts[0])
            # Close the tag and get the result
            result = tag_stack[-1].send((TAG_CLOSE_MSG, parts[1]))
            # Remove the closed tag
            tag_stack.pop(-1)
            # Feed the result to the wrapping tag (if any), else write it.
            if tag_stack:
                tag_stack[-1].send(result)
            else:
                ostream.write(result)
            line = parts[-1]

        # Write the rest of the line
        if line:
            if tag_stack:
                tag_stack[-1].send(line)
            else:
                ostream.write(line)
            line = ''


processor(open('/home/ehwaal/admingen/projects/xml_server/hmi.xml'), sys.stdout)
