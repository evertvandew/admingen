
from unittest import TestCase
from threading import Thread
import os, os.path
import time
import asyncio
import socket
import threading

from admingen.dbengine import readconfig
from admingen.htmltools import simpleCrudServer, runServer, Page
from admingen.servers import *


TESTDB = 'test.db'



class ServerTests(TestCase):
    def setUp(self):
        # Delete the database if there is one left-over
        if False and os.path.exists(TESTDB):
            os.remove(TESTDB)

    def testCrudServer(self):
        """ Test the simple CRUD server generated on the tables of uren_crm """
        # Parse the uren_crm details
        with open('uren_crm.txt') as f:
            transitions, db, dbmodel = readconfig(f)
        # Instantiate the database
        db.bind(provider='sqlite', filename=TESTDB, create_db=True)
        db.generate_mapping(create_tables=True)

        # Create the server
        server = simpleCrudServer(dbmodel, Page)
        # Run the server in a thread
        runner = Thread(target=runServer, args=(server, {}))
        runner.setDaemon(True)
        runner.start()

        while True:
            time.sleep(1)

    def testKeyring(self):

        @keychain_unlocker('test.enc')
        class Test:
            Page = staticmethod(Page)

            @cherrypy.expose
            def index(self):
                return self.Page('Hello, World!')

        cherrypy.quickstart(Test(), '/')


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

        server = mkUnixServer(Worker(), path)
        loop.create_task(server)

        def testcase():
            proxy = unixproxy(Worker, path)
            proxy.hi(10)
            proxy.ho('Hallo daar')
            r = proxy.it()
            print (r)
            loop.stop()
            proxy.hi(10)

        th = threading.Thread(target=testcase)
        th.setDaemon(True)
        th.start()

        loop.run_forever()
