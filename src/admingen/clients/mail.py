
import logging
import markdown
import os.path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate



def constructMail(md_msg, attachment_files, **headers):
    # TODO: Add support for multiple recipients
    # We are using the old API for constructing emails:
    # the new one does not encode PDF attachments correctly.

    outer = MIMEMultipart()
    for key, value in headers.items():
        outer[key] = value

    outer['Date'] = formatdate(localtime=True)
    html_msg = markdown.markdown(md_msg)

    text_parts = MIMEMultipart('alternative')
    msg_plain = MIMEText(md_msg)
    msg_html = MIMEText(html_msg, 'html')
    text_parts.attach(msg_plain)
    text_parts.attach(msg_html)
    outer.attach(text_parts)


    for fullname in attachment_files:
        overzicht = open(fullname, 'rb').read()
        extension = fullname.split('.')[-1]
        fname = os.path.basename(fullname)
        overzicht_part = MIMEApplication(overzicht, extension, name=fname)
        outer.attach(overzicht_part)

    return outer



def sendmail(mailfrom, receivers, body, subject, smtp_c, attachments=[], cc=[], bcc=[]):
    if isinstance(receivers, str):
        receivers = [receivers]
    if isinstance(attachments, str):
        attachments = [attachments]
    if isinstance(cc, str):
        cc = [cc]
    if isinstance(bcc, str):
        bcc = [bcc]

    to_adres = ', '.join(receivers)
    msg = constructMail(body, attachments, To=to_adres, From=mailfrom,
                        Subject=subject,
                        **{'Reply-To': mailfrom},
                        cc=', '.join(cc),
                        bcc=', '.join(bcc))

    smtp_c.sendmail(mailfrom, to_adres, bytes(msg))
    logging.info('Sent email to %s' % to_adres)
