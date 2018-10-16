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
    def read_begin():
        # Read a record
        for line in stream:
            if line.beginswith('BEGIN'):
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

    timezone = None
    daylight = None
    while True:
        record_type = read_begin()
        # Skip VCALENDAR pre-ambles
        if record_type == 'VCALENDAR':
            continue
        # Handle timezones
        if record_type == 'VTIMEZONE':
            # We now get either a STANDARD or DAYLIGHT record
            # Remember only the latest
            tz_type = read_begin()
            if tz_type == 'STANDARD':
                timezone = read_details(tz_type)
            if tz_type == 'DAYLIGHT':
                daylight = read_details(tz_type)
            read_end(record_type)
        # Handle appointments ('VEVENTS')
        if record_type == 'VEVENT':
            details = read_details(record_type)
