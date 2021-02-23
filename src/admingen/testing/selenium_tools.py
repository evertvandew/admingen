""" A collection of usefull tools for testing with selenium, """

from selenium import webdriver
import unittest
import json
import os
import os.path
import time

server = 'http://localhost:5000'
db_path = '../data'


def ensure_login(name, password):
    """ A decorator that checks a specific user is logged in before
        calling the relevant function.
    """
    def wrapper(func):
        def doIt(self):
            token = self.driver.get_cookie('token_data')
            uname = self.driver.get_cookie('user_name')
            if not token or uname != name:
                self.login(name, password)
            return func(self)
        return doIt
    return wrapper



class SeleniumTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.driver = webdriver.Firefox()
        # Ensure there is no login tokens lurking around...
        cls.driver.get(f"{server}/logout")
        cls.to_delete = []

    @classmethod
    def tearDownClass(cls) -> None:
        cls.driver.close()
        for f in cls.to_delete:
            table, condition = f
            dir = f'{db_path}/{table}'
            for fname in os.listdir(dir):
                thefile = dir + '/' + fname
                if not os.path.isfile(thefile):
                    continue
                with open(thefile) as ff:
                    details = json.load(ff)
                if eval(condition, details):
                    os.remove(thefile)

    def add_cleanup(self, table, condition):
        self.to_delete.append((table, condition))

    def get_element(self, key):
        w = None
        if key.startswith('#'):
            w = self.driver.find_element_by_id(key[1:])
        elif key.startswith('@'):
            w = self.driver.find_element_by_name(key[1:])
        else:
            w = self.driver.find_element_by_xpath(key)
        assert w, f"Could not find widget {key}"
        return w

    def set(self, key, value=None):
        if isinstance(key, list):
            for k, v in key:
                self.set(k, v)
            return
        w = self.get_element(key)
        w.clear()
        w.send_keys(value)

    def set_select(self, key, value):
        if key.startswith('#'):
            xp = f'//select[@id="{key[1:]}"]/option[text()="{value}"]'
        w = self.driver.find_element_by_xpath(xp)
        w.click()


    def login(self, uname, password):
        if self.driver.get_cookie('token_data'):
            self.driver.get(f"{server}/logout")
        self.driver.get(f"{server}")
        self.set([('#uname', uname),
                  ('#psw', password)])
        self.click("//input[@value='inloggen']")

    def get_value(self, tag_key):
        """ Return the value from an input. Ensure it is not empty. """
        while not (cid := self.get_element(tag_key).get_attribute("value")):
            time.sleep(0.1)
        return cid


    def click(self, key):
        w = self.get_element(key)
        w.click()



