
from contextlib import contextmanager
import time
import os
import json
import datetime

from dataclasses import dataclass, asdict, is_dataclass

@contextmanager
def quitter(item):
    """ Make sure the item is 'quit' """
    try:
        yield
    finally:
        item.quit()



class DownloadError(RuntimeError):
    pass

def findNewFile(downloaddir, files, extension, check=None):
    # Wait until a new CSV file appears
    start = time.time()
    while True:
        time.sleep(0.1)
        # This is safe, because Chrome will only rename the file to its final name when complete
        new_files = [f for f in os.listdir(downloaddir) if
                     f not in files and f.lower().endswith(extension)]
        if new_files:
            return os.path.join(downloaddir, new_files[0])
        # Wait at most 5 minutes until the download is complete
        if time.time() - start > 5 * 60:
            raise RuntimeError('Download not complete in time')
        if check and not check():
            raise DownloadError('Predicate returned an error')


def checkExists(dirname):
    if not os.path.exists(dirname):
        os.makedirs(dirname)

class EmptyClass:
    pass


def isoweekno2day(year:int, week:int, dow:int=0):
    """ Return the datetime for a specific iso week.
        This function is the inverse of date.isocalendar.
    """
    # Use the (non-iso) strptime, then correct for the right week.
    # The strptime week starts at sunday, ISO's at monday.
    d = datetime.datetime.strptime('%i%i%i'%(year, week, dow+1), '%Y%W%w')
    details = d.isocalendar()
    err = week - details[1]
    return d + datetime.timedelta(7*err, 0)



class DataJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if is_dataclass(o):
            return asdict(o)
        return json.JSONEncoder.default(self, o)


def dumps(o):
    return json.dumps(o, cls=DataJsonEncoder)

def loads(s):
    return json.loads(s)