import os, time, asyncio
import ssl
from aiosmtpd.controller import Controller

PORT = 8025

callback = None

class Handler:
    async def handle_DATA(self, server, session, envelope):
        if callback:
            callback(envelope.mail_from,
                     envelope.rcpt_tos,
                     envelope.content.decode('utf8', errors='replace'))
        return '250 OK'


def loop ():
    controller = Controller(Handler(), hostname='0.0.0.0', port=PORT)
    controller.start()
    return controller

if __name__=='__main__':
    loop()
