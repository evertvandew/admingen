#!/usr/bin/env python3
import os, time, asyncio
import ssl
from aiosmtpd.smtp import SMTP
from aiosmtpd.controller import Controller

PORT = 8025

callback = None

context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain('cert.pem', 'key.pem')

class Handler:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        envelope.rcpt_tos.append(address)
        return '250 OK'

    async def handle_DATA(self, server, session, envelope):
        if callback:
            callback(envelope.mail_from,
                     envelope.rcpt_tos,
                     envelope.content.decode('utf8', errors='replace'))
        print(f'Message from {envelope.mail_from}')
        print(f'Message for {envelope.rcpt_tos}')
        print(f'Message data:\n{envelope.content.decode("utf8", errors="replace")}')
        print('End of message')
        return '250 OK'


class AuthSMTP(SMTP):
    @asyncio.coroutine
    def smtp_AUTH(self, arg):
        if arg != 'PLAIN':
            yield from self.push('501 Syntax: AUTH PLAIN')
            return
        yield from self.push('334')
        try:
            second_line = yield from self._reader.readline()
        except (ConnectionResetError, asyncio.CancelledError) as error:
            # How to recover here?
            return
        try:
            second_line = second_line.rstrip(b'\r\n').decode('ascii')
        except UnicodeDecodeError:
            yield from self.push('500 Error: Challenge must be ASCII')
            return
        if second_line == 'dGVzdAB0ZXN0ADEyMzQ=':
            self.authenticated = True
            yield from self.push('235 Authentication successful')
        else:
            yield from self.push('535 Invalid credentials')


class MyController(Controller):
    def factory(self):
        return AuthSMTP(self.handler, enable_SMTPUTF8=self.enable_SMTPUTF8)

def loop ():
    controller = Controller(Handler(), hostname='0.0.0.0', port=PORT, ssl_context=context)
    controller.start()
    return controller

if __name__=='__main__':
    ctrl = loop()
    input('Press enter to stop')
    ctrl.stop()
