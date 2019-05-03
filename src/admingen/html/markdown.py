#!/usr/bin/env python3
""" Parser for handling Mardown extensions, notably the input fields and navigation buttons.

The new items are entered using an HTML (XML) syntax, because it is so powerful & flexible.
"""

import re
import sys
import io
import argparse


TAG_CLOSE_MSG = '__TAG_CLOSE__'


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


def Tag(handler):
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



def handle_form(args, lines):
    return '''<form>
    {0}
    <input type="submit" value="{args[submit]}">
</form>'''.format(lines, args=args)

def handle_field(args, lines):
    name = args['name']
    text = args.get('text', name)
    itype = args.get('type', 'text')
    return '''<label>
        {1}:
        <input type="{2}" name="{0}" />
</label>'''.format(name, text, itype)


def handle_page(args, lines):
    return 'Pagina: {0}'.format(''.join(lines))

def handle_resourceeditor(args, lines):
    return 'Hier komt een resource editor: %s' % args

def handle_largebutton(args, lines):
    return 'Hier komt een grote knop: %s' % args



generators = {'Page': Tag(handle_page),
              'LargeButton': Tag(handle_largebutton),
              'ResourceEditor': Tag(handle_resourceeditor),
              'Field': Tag(handle_field),
              'Form': Tag(handle_form)}

my_tags = list(generators.keys())

def processor(istream, ostream):
    without_comments = io.StringIO()
    filterComment(istream, without_comments)
    # Make the stream readable
    without_comments.seek(0)

    # Prepare a RE to find all custom tags
    wrapped_tags = '|'.join('(%s)' % t for t in my_tags)
    tag_start = re.compile(r'<(%s)' % wrapped_tags)
    tag_end = re.compile(r'</(%s)>' % wrapped_tags)
    # XML tags can have two endings: "/>" or ">".
    argsend = re.compile(r'([^"/>]|("[^"]*?"))*(/?>)')

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

def test():
    argument_test = '''  bla1 = "123hijqew&amp;"  sta1="Dit
 is een test" 
 '''

    a = argument_parser()
    a.send(None)
    for line in argument_test.splitlines(keepends=True):
        a.send(line)
    result = a.send((TAG_CLOSE_MSG, 'bla'))
    assert result == {'bla1': "123hijqew&amp;",
                      'sta1': "Dit\n is een test"}

    comment_test = ''' Line 1 <!--
        Comment
        Comment --> line 2
<!-- comment --> line 3'''

    result = io.StringIO()
    filterComment(io.StringIO(comment_test), result)
    result = result.getvalue()
    assert result == ''' Line 1  line 2
 line 3'''

if __name__ == '__main__':
    if False:
        test()
        sys.exit(0)
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', default='-')
    args = parser.parse_args()

    instream = sys.stdin if args.input == '-' else open(args.input)
    processor(instream, sys.stdout)
