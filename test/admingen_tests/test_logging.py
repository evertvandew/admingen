""" Test the logging settings that are set by the config handler """

# Let the tmp think we are running in production mode.
import os
import os.path
import logging
import glob

os.environ['PROGRAMNAME'] = 'admingen'

from unittest import TestCase


# The logging is configured in the tmp module.
import admingen.config


class logtests(TestCase):
    def tearDown(self):
        # Get the log files and delete them
        files = glob.glob('*.log')
        files += glob.glob('*.log.*')
        for f in files:
            os.remove(f)
    def testit(self):
        # Check a non-default handler was installed
        logger = logging.getLogger()
        self.assertTrue(logger.handlers)
        self.assertNotEqual(type(logger.handlers[0]), logging.StreamHandler)
        # Generate a log of logging (about 50MB-worth)
        msg = 'testmessage ' * 100  # About 1K per message
        for _ in range(60000):
            logging.error(msg)

        # Check the log files are created
        logfiles = glob.glob(admingen.config.projectname+'.log*')
        self.assertEqual(len(logfiles), 6)
