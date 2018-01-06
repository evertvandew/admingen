
from contextlib import contextmanager
import time
import os


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