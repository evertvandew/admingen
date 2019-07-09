""" Handle an hour-registration in ical format.

It is assumed that all events in the calendar should be matched to customers / projects.
"""


from dataclasses import dataclass
import datetime

@dataclass
class Event:
    start: datetime.datetime
    end: datetime.datetime
    description: str
    summary: str


def ical_reader(stream, period_start=None, period_end=None):
    """ Generator that parses the ICAL file and yields Event objects """
    standard = None
    daylight = None
    daylight_start = {}
    daylight_end = {}

    def read_begin():
        # Read a record
        for line in stream:
            if line.startswith('BEGIN'):
                record_type = line.strip().split(':')[1]
                return record_type
    def read_details(terminator):
        # Read the details of a record
        details = {}
        for line in stream:
            if ':' in line:
                key, value = line.strip().split(':', 1)
                if key == 'END' and value == terminator:
                    return details
                details[key] = value
    def read_end(terminator):
        for line in stream:
            if 'END:%s'%terminator in line:
                return
    def handle_time(t):
        # Convert the JSON time into a proper datetime object
        pass
    def correct_timezone(dt: datetime.datetime):
        """ Correct a datetime for the current timezone, taking daylight saving into account. """
        year = dt.year
        if not dt.year in daylight_start:
            # Find the sundays directly before 1-4 and 1-11.
            s = datetime.datetime(dt.year, 4, 1, 2)
            s -= datetime.timedelta(s.weekday()+1)
            e = datetime.datetime(dt.year, 11, 1, 2)
            e -= datetime.timedelta(e.weekday()+1)
            daylight_start[dt.year] = s
            daylight_end[dt.year] = e

        if daylight_end[dt.year] > dt > daylight_start[dt.year]:
            tz = int(daylight['TZOFFSETTO'][:3])
        else:
            tz = int(daylight['TZOFFSETFROM'][:3])
        return dt + datetime.timedelta(0, 3600*tz)

    while True:
        record_type = read_begin()
        if record_type is None:
            return
        # Skip VCALENDAR pre-ambles
        if record_type == 'VCALENDAR':
            continue
        # Handle timezones
        if record_type == 'VTIMEZONE':
            # We now get either a STANDARD or DAYLIGHT record
            # Remember only the latest
            tz_type = read_begin()
            if tz_type == 'STANDARD':
                standard = read_details(tz_type)
            if tz_type == 'DAYLIGHT':
                daylight = read_details(tz_type)
            read_end(record_type)
        # Handle appointments ('VEVENTS')
        if record_type == 'VEVENT':
            details = read_details(record_type)
            # Apply the correct time-zone to each time-related record
            for tkey in 'DTSTART DTEND DTSTAMP CREATED LAST-MODIFIED'.split():
                if tkey in details:
                    value = details[tkey]
                    dt_value = datetime.datetime.strptime(value, '%Y%m%dT%H%M%SZ')
                    dt_value = correct_timezone(dt_value)
                    details[tkey] = dt_value
            yield details
