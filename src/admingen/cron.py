""" A set of functions that are useful for handling repetative tasks """

from datetime import datetime, date, timedelta
import dataclasses as dc
from typing import Union, List
import threading
import logging
import time


@dc.dataclass
class Range:
    start: int = 0
    end: int = None
    step: int = 1


range_set = Union[int, Range, List[Union[int, Range]]]


def fits_in_range(range, value):
    """ Return true if a value fits in the range. """
    if range is None:
        return True
    if isinstance(range, Range):
        return (value - range.start) % range.step == 0
    if isinstance(range, list):
        return any(fits_in_range(r, value) for r in range)


def find_next_in_range(range, start, limit, minimum=0):
    """ Returns an integer as the next in the sequence, and a bool to indicate if
        the sequence wrapped around.
    """
    wrap = False
    if range is None:
        # Just increment the item by one and wrap around if necessary
        n = start + 1
        if n >= limit:
            n -= limit
            wrap = True
        return n, wrap
    if isinstance(range, int):
        return range, range <= start
    if isinstance(range, Range):
        if start < range.start:
            return range.start, False
        index = (start - range.start) // range.step
        n = range.step * (index + 1) + range.start
        if (range.end and n > range.end) or \
                n >= (limit + minimum):
            n = range.start or minimum
            wrap = True
        return n, wrap
    if isinstance(range, list):
        # Keep track of which item in the list is the closest next entry
        options = [find_next_in_range(r, start, limit)[0] for r in range]
        options = sorted(options)
        if options[-1] <= start:
            return options[0], True
        if options[0] > start:
            return options[0], False
        for r in options:
            if r > start:
                return r, False
    raise RuntimeError(f"Unsupported type for range: {type(range)}")


@dc.dataclass
class CronSchedule:
    minute: range_set = None  # Minute count, 0-59
    hour: range_set = None  # Hour count, 0-23
    dom: range_set = None  # Day of Month, 1-32 (depending on month)
    month: range_set = None  # Month number, 1-12
    dow: range_set = None  # Day of Week, 0-6
    wdom: range_set = None  # Week of Month, 0-4
    
    def next_action(self, start: datetime = None):
        start = start or datetime.now()
        hour = start.hour
        day = start.day
        month = start.month
        year = start.year
        minute, wrap = find_next_in_range(self.minute, start.minute, 60)
        # See if we went to the next hour
        if wrap:
            hour, wrap = find_next_in_range(self.hour, start.hour, 24)
        
        # We enter a loop to find a day that matches all criteria that apply to days
        # There are 4: day range, month range, dow range, wdom range.
        # It is hard to find a solution in one go, so we try the brute force approach.
        valid = False
        while not valid:
            # See if we went to the next day
            if wrap:
                # The simple case: look for a valid day in the current month
                days_in_month = 30 if month in [4, 6, 9, 11] else 31
                if month == 2:
                    # Calculate leap years according to the gregorian calendar
                    days_in_month = 29 if ((year % 4 == 0) and not (year % 100 == 0)) or (
                                year % 400 == 0) else 28
                day, wrap = find_next_in_range(self.dom, start.day, days_in_month, minimum=1)
            
            # See if we went to the next month
            if wrap:
                month, wrap = find_next_in_range(self.month, start.month, 12, minimum=1)
            
            # Finally, increment the year if necessary.
            if wrap:
                year += 1
            
            # Now we need to be careful: check on dow and wdom.
            # We need to find a date that matches both, if applicable.
            valid = True
            d = date(year, month, day)
            if self.dow is not None:
                valid = fits_in_range(range.dow, d.weekday())
            
            # First check the situation where a wdom is set.
            if self.wdom is not None:
                valid = valid and fits_in_range(range.wdom, d.day // 7)
        
        return datetime(year, month, day, hour, minute, 0)
    
    @staticmethod
    def parse(s):
        """ Parse a crontab schedule string and create a Cron object from it.
            The string consists of a set of whitespace-separated ranges for respectively
            minutes, hours, days and months, with optional day of week and week of month ranges.
            
            The ranges are set using either:
                An astrix to match any value
                An integer defining a specific value
                A comma-separated list of specific values
                A range indicated by two integers separated by a dash,
                with optionally a step after a slash
            
            For example: 0 */4 * * 0-4 *
            
            Will trigger every four hours at the hour, for all working days.
        """
        def parse_part(s):
            if ',' in s:
                result = [parse_part(i) for i in s.split(',')]
                return result
            if '-' in s:
                parts = s.split('-', maxsplit=1)
                if '/' in parts[1]:
                    end, step = parts[1].split('/', maxsplit=1)
                    return Range(int(parts[0]), int(end), int(step))
            elif '/' in s:
                # Now the only other part must be an astrix
                parts = s.split('/', maxsplit=1)
                assert parts[0] == '*'
                return Range(0, None, int(parts[1]))
            elif s.startswith('*'):
                return None
            return int(s)
        
        parts = s.split()
        ranges = [parse_part(p) for p in parts]
        return CronSchedule(*ranges)


def scheduled_action(cron_schedule):
    """ Decorator that makes an action run periodically. """
    def wrap(action):
        def run():
            cron = CronSchedule.parse(cron_schedule)
            while True:
                # Calculate when to activate
                next_action = cron.next_action()
                activate_ts = next_action.timestamp()
                
                # Wait to activate. Work in 1-minute steps
                # to avoid problems with a change in system time.
                while (t := time.time()) < activate_ts:
                    # Ensure synchronisation on a whole minute.
                    n = 60 - (t % 60)
                    time.sleep(n)
                
                # Trigger the action
                try:
                    action()
                except:
                    logging.exception('Error executing scheduled action!')
        def start():
            th = threading.Thread(target=run)
            th.daemon = True
            th.start()
        
        return start
    return wrap

def tests():
    # Test the updating of dates and times.
    fmt = '%d-%m-%Y %H:%M'
    dt = datetime.strptime('1-1-2020 00:00', fmt)
    c = CronSchedule.parse('0 */8 1,15')
    e = ['1-1-2020 8:00', '1-1-2020 16:00', '15-1-2020 0:00', '15-1-2020 8:00', '15-1-2020 16:00',
         '1-2-2020 0:00', '1-2-2020 8:00', '1-2-2020 16:00', '15-2-2020 0:00', '15-2-2020 8:00',
         '15-2-2020 16:00']
    e = [datetime.strptime(t, fmt) for t in e]
    
    for check in e:
        dt = c.next_action(dt)
        assert check == dt
    
    # Test the generation of single ranges.
    ranges = [[3, Range(7, 13, 3)], Range(0, 10), Range(1, 10, 2), [1, 9, 11]]
    expecteds = [
        [3, 3, 3, 7, 7, 7, 7, 10, 10, 10, 13, 13, 13, 3, 3],
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 0, 0, 0, 0, 0],
        [1, 3, 3, 5, 5, 7, 7, 9, 9, 1, 1, 1, 1, 1, 1],
        [1, 9, 9, 9, 9, 9, 9, 9, 9, 11, 11, 1, 1, 1, 1]
    ]
    for r, e in zip(ranges, expecteds):
        l = [find_next_in_range(r, i, 14)[0] for i in range(15)]
        assert l == e

if __name__ == '__main__':
    tests()
