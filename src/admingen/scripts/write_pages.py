#!/usr/bin/env python3
"""
Take a XML-server definition, and take out the Page tags, add some HTML overhead and
write them to the file system as static pages.
"""

import argparse
from admingen.xml_template import processor, Tag, debug_render, Template
import os, os.path
import sys
import json
import markdown
from mako.template import Template, DefTemplate


page_template = Template("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />
        <title>${title}</title>

    ${dependencies}


</head>
<body style="margin-top:0px;height:100vh">
<div id="ackDelete" class="modal" tabindex="-1" role="dialog">
  <div class="modal-dialog" role="document">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Bevestig verwijderen</h5>
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
      <div class="modal-body">
        <p id="error-reporter">Weet je het zeker?</p>
      </div>
      <div class="modal-footer">
        <button id="ackDeleteYes" type="button" class="btn btn-primary">Yes</button>
        <button id="ackDeleteNo" type="button" class="btn btn-secondary" data-dismiss="modal">No</button>
      </div>
    </div>
  </div>
</div>
<div id="notification" class="modal" tabindex="-1" role="dialog">
  <div class="modal-dialog" role="document">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title"></h5>
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
      <div class="modal-body">
        <i id="notification_icon" style="font-size:30pt;width:2em"></i><span id="notification_message">Weet je het zeker?</span>
      </div>
      <div class="modal-footer">
        <button id="ack" type="button" class="btn btn-secondary" data-dismiss="modal">Ok</button>
      </div>
    </div>
  </div>
</div>
<script>
    function show_info(msg) {
        let icon = $("i[id='notification_icon']")[0];
        icon.className = "";
        icon.classList.add('fa');
        icon.classList.add('fa-info-circle');
        icon.style.color = "#0050B6";
        $("#notification_message")[0].innerHTML = msg;
        $("div[id='notification']").modal('show');
        $("#notification").find(".modal-title")[0].innerHTML = "Kennisgeving";
    }
    function show_error(msg) {
        let icon = $("i[id='notification_icon']")[0];
        icon.className = "";
        icon.classList.add('fa');
        icon.classList.add('fa-exclamation-circle');
        icon.style.color = "#D73A2B";
        $("#notification_message")[0].innerHTML = msg;
        $("div[id='notification']").modal('show');
        $("#notification").find(".modal-title")[0].innerHTML = "Foutmelding";
    }
    
    function getCookie(key) {
        var keyValue = document.cookie.match('(^|;) ?' + key + '=([^;]*)(;|$)');
        return keyValue ? keyValue[2] : null;
    }
    function setCookie(cname, cvalue) {
      const d = new Date();
      d.setTime(d.getTime() + (366*24*60*60*1000));
      let expires = "expires="+ d.toUTCString();
      document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
    }   

    function acm_authorized(roles) {
        var role = getCookie("role_name");
        var allowed_roles = roles.split(',');
        return allowed_roles.includes(role);
    }
    
    function now() {
        var today = new Date();
        var dd = String(today.getDate()).padStart(2, '0');
        var mm = String(today.getMonth() + 1).padStart(2, '0'); //January is 0!
        var yyyy = today.getFullYear();
        var hh = String(today.getHours()).padStart(2, '0');
        var m = String(today.getMinutes()).padStart(2, '0');
        today = dd + '-' + mm + '-' + yyyy + ' ' + hh + ':' + m + ':00';
        return today;
    }
    function show_message(key, type, title, msg, buttons) {
        let icon = $("#notification_icon")[0];
        icon.className = "";
        icon.classList.add('fa');
        if (type==1) {
            icon.classList.add('fa-check-circle');
            icon.style.color = "#00B60A";
        } else if (type==2) {
            icon.classList.add('fa-info-circle');
            icon.style.color = "#0050B6";
        } else if (type==3) {
            icon.classList.add('fa-question-circle');
            icon.style.color = "#0050B6";
        } else if (type==4) {
            icon.classList.add('fa-exclamation-circle');
            icon.style.color = "#ffa500";
        } else if (type==5) {
            icon.classList.add('fa-exclamation-circle');
            icon.style.color = "#ff0000";
        }
        $("#notification_message")[0].innerHTML = msg;
        $("#notification .modal-title")[0].innerHTML = title;
        buttons_txt = ''
        buttons.forEach(function(txt) {
            buttons_txt += '<button type="button" class="btn btn-secondary" data-dismiss="modal" onclick="route('+"'"+key+'/'+txt+"'"+')">'+txt+'</button>';
        });
        $("div[id='notification']  .modal-footer")[0].innerHTML = buttons_txt;
        $("div[id='notification']").modal('show');
    }
    function get_parameter(param) {
        const urlParams = new URLSearchParams(window.location.search);
        const myParam = urlParams.get(param);
        return myParam;
    }
    $(document).ready(function(){
        $.ajaxSetup({
            cache: false,
        });

        $("#div_current_user").each(function(i){
            this.innerHTML = getCookie("uname");
        });
    });
</script>
${heading}
${lines}
${footer}
</body>
</html>""")


created_pages = []
current_page_context = dict(
    headers='',
    title='admingen',
    heading='',
    footer='',
    acm='user,editor,administrator',
    dependencies=''
)

def handle_Page(args, lines):
    """ Handle a page definition by writing the HTML inside it to file. """
    url = args['url']
    assert ':' not in url
    if url in created_pages:
        raise RuntimeError('Creating page', url, 'for the second time')
    text = page_template.render(lines=lines, **current_page_context)
    dirname, fname = os.path.split('html/'+url.strip('/'))

    # Expand any Mako templates inside the page.
    t = Template(text)
    text = debug_render(t)

    # Write the result to file
    print ('Writing:', dirname, fname)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    with open(os.path.join(dirname, fname), 'w') as out:
        out.write(text)
    return ''


def handle_PageContextValue(args, lines):
    """ Let the user modify a value in the page context.
        This value is used for all subsequent pages.
    """
    assert 'name' in args
    name = args['name']
    if name in current_page_context and args.get('action', '') == 'append':
        current_page_context[name] += lines
    else:
        current_page_context[name] = lines
    return ''


def handle_Markdown(args, lines):
    md = markdown.markdown(''.join(lines))
    return md

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', '-f', default=None)
    args = parser.parse_args()
    stream = open(args.file) if args.file else sys.stdin
    processor({'Page': Tag('Page', handle_Page),
               'PageContextValue': Tag('PageContextValue', handle_PageContextValue),
               'MarkDown': Tag('MarkDown', handle_Markdown)
               },
              stream)

if __name__ == '__main__':
    run()