
from unittest import TestCase
from threading import Thread
import os, os.path
import time
import asyncio
import socket
import threading

import requests

from admingen.appengine import readconfig
from admingen.htmltools import simpleCrudServer, runServer, Page
from admingen.servers import *


TESTDB = 'test.db'



class ServerTests(TestCase):
    def setUp(self):
        # Delete the database if there is one left-over
        if os.path.exists(TESTDB):
            os.remove(TESTDB)

    def testCrudServer(self):
        """ Test the simple CRUD server generated on the tables of uren_crm """
        # Parse the uren_crm details
        with open('uren_crm.txt') as f:
            model = readconfig(f)
        transitions, db, dbmodel = model.fsmodel, model.db, model.dbmodel
        # Instantiate the database
        db.bind(provider='sqlite', filename=TESTDB, create_db=True)
        db.generate_mapping(create_tables=True)

        # Create the server
        server = simpleCrudServer(dbmodel, Page)
        # Run the server in a thread
        runner = Thread(target=runServer, args=(server, {}))
        runner.setDaemon(True)
        runner.start()

        url = 'http://localhost:8080/Klant'

        while True:
            # Wait until the server is in the air
            try:
                r = requests.get('http://localhost:8080')
                break
            except requests.exceptions.ConnectionError:
                time.sleep(0.1)

        # Now try to create some objects
        r = requests.get(url+'/add')
        self.assertEqual(r.status_code, 200)
        self.assertIn('<form action="/Klant/add" method="post" enctype="multipart/form-data" class="form-horizontal">', r.text)
        self.assertIn('<input type="text" class="form-control" name="naam"  value=""/>', r.text)
        self.assertIn('<select name="contactpersoon"></select>', r.text)

        params = {'naam': 'Dynniq', 'id': None}
        r = requests.post(url+'/add', params = params)
        self.assertEqual(r.status_code, 200)

        # Check the new klant is in the database
        r = requests.get(url)
        self.assertEqual(r.status_code, 200)
        expect = '''<tr onclick="javascript:location.href='view?id=1'"><td>1</td>
<td>Dynniq</td>
<td>None</td></tr>'''
        self.assertIn(expect, r.text)

        # Try to update it
        r = requests.get(url+'/edit', params={'id':'1'})
        self.assertEqual(r.status_code, 200)
        params = {'naam': 'Peek Traffic', 'id': '1'}
        r = requests.post(url + '/edit', params=params)
        r = requests.get(url)
        self.assertEqual(r.status_code, 200)
        expect = '''<tr onclick="javascript:location.href='view?id=1'"><td>1</td>
<td>Peek Traffic</td>
<td>None</td></tr>'''
        self.assertIn(expect, r.text)


    def testUnixSockets1(self):
        path = '/home/ehwaal/tmp/testsock'
        loop = asyncio.get_event_loop()

        async def handler(reader, writer):
            while True:
                data = await reader.readline()
                print (data)
                if b'exit' in data:
                    loop.stop()
                    return
                writer.writelines([data])

        server = asyncio.start_unix_server(handler, path)
        loop.create_task(server)

        async def testcase():
            reader, writer = await asyncio.open_unix_connection(path)
            writer.write(b'test\n')
            d = await reader.readline()
            print ('>>>', d)
            writer.write(b'Hallo, wereld!\n')

            writer.write(b'exit\n')

        loop.create_task(testcase())
        loop.run_forever()

    def testUnixSockets(self):
        path = '/home/ehwaal/tmp/testsock'
        if os.path.exists(path):
            os.remove(path)

        loop = asyncio.get_event_loop()

        def testcase():
            while not os.path.exists(path):
                time.sleep(0.1)

            s = socket.socket(socket.AF_UNIX)
            s.connect(path)

            s.send(b'test\n')
            d = s.recv(1024)
            print ('>>>', d)
            s.send(b'Hallo, wereld\n')
            s.send(b'exit\n')

        async def handler(reader, writer):
            while True:
                data = await reader.readline()
                print (data)
                if b'exit' in data:
                    loop.stop()
                    return
                writer.writelines([data])

        server = asyncio.start_unix_server(handler, path)
        loop.create_task(server)

        th = threading.Thread(target=testcase)
        th.setDaemon(True)
        th.start()

        loop.run_forever()

    def testUnixServer(self):
        path = '/home/ehwaal/tmp/testsock'
        loop = asyncio.get_event_loop()

        @Message
        class Details:
            a: str
            b: int

        class Worker:
            @expose
            def hi(self, i:int):
                print ('Hi ', i)
            @expose
            def ho(self, s:str):
                print ('Ho', s)
            @expose
            def it(self):
                return 'Dit is', 1, 'test'
            @expose
            def hit(self, details:Details):
                print (details)

        server = mkUnixServer(Worker(), path)
        loop.create_task(server)

        def testcase():
            proxy = unixproxy(Worker, path)
            proxy.hi(10)
            proxy.ho('Hallo daar')
            r = proxy.it()
            print (r)
            proxy.hit(Details('hallo', 1234))
            loop.stop()
            proxy.hi(10)

        th = threading.Thread(target=testcase)
        th.setDaemon(True)
        th.start()

        loop.run_forever()

    def testCliInterface(self):
        path = '/home/ehwaal/tmp/testsock'
        loop = asyncio.get_event_loop()

        @Message
        class Details:
            a: str
            b: int

        class Worker:
            @expose
            def hi(self, i:int):
                print ('Hi ', i)
            @expose
            def ho(self, s:str):
                print ('Ho', s)
            @expose
            def it(self):
                return 'Dit is', 1, 'test'
            @expose
            def hit(self, details:Details):
                print ('HIT', details)

        server = mkUnixServer(Worker(), path)
        loop.create_task(server)


        # Open the UNIX socket
        with socket.socket(socket.AF_UNIX) as sock:
            while True:
                loop.run_until_complete(asyncio.sleep(0.1))
                sock.connect(path)
                break

            loop.run_until_complete(asyncio.sleep(0.1))
            print (sock.recv(4096))

            # Send a command
            sock.send(b'hi\n345\n')
            # Let the server handle it
            loop.run_until_complete(asyncio.sleep(0.1))
            # TODO: Add check

            # Send another command
            sock.send(b'hit\nHallo\n777\n')
            loop.run_until_complete(asyncio.sleep(0.1))
            # FIXME: this fails!
