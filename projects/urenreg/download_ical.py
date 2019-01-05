import datetime
import sys
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools
from admingen.data import CsvReader, CsvWriter, dataline
from admingen.util import isoweekno2day
import re


calendarId = 'h66vatlgj8e3lh2fkd5p2arvps@group.calendar.google.com'
week = (2018, 51)



# Determine details of the current tasks
taskconfig = '/home/ehwaal/Documents/uurstaten/urendata.csv'
tasks = CsvReader(taskconfig)


# If modifying these scopes, delete the file token.json.
SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'

"""Shows basic usage of the Google Calendar API.
Prints the start and name of the next 10 events on the user's calendar.
"""
store = file.Storage('token.json')
creds = store.get()
if not creds or creds.invalid:
    flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
    creds = tools.run_flow(flow, store)
service = build('calendar', 'v3', http=creds.authorize(Http()))

# Call the Calendar API
s = isoweekno2day(week[0], week[1])
weekstart = s.isoformat() + 'Z'
weekend = (s + datetime.timedelta(6, 24*60*60-1)).isoformat() + 'Z'

events_result = service.events().list(calendarId=calendarId, timeMin=weekstart,
                                    timeMax=weekend, singleEvents=True,
                                    orderBy='startTime').execute()
events = events_result.get('items', [])

proj_weekdata = {}


if not events:
    print('No urenregistraties found.')
for event in events:
    start = event['start'].get('dateTime', event['start'].get('date'))

    # Find the opdrachtnr for the current event
    opdrachtnr = None
    for opdracht in tasks['Opdracht']:
        if opdracht.naam.lower() in event['summary'].lower():
            for kw in opdracht.keywords.split():
                if re.search(kw, event['summary'].lower()):
                    opdrachtnr = opdracht.id
                    break

    if not opdrachtnr:
        print ('Could not find opdracht for %s'%event['summary'], file=sys.stderr)
        continue


    starttime = datetime.datetime.fromisoformat(event['start']['dateTime'])
    endtime = datetime.datetime.fromisoformat(event['end']['dateTime'])

    y, w, daynr = starttime.date().isocalendar()
    weeknr = '%s%s'%(y, w)

    # Calculate the duration of the work in hours
    duration = (endtime - starttime).seconds / 3600
    # If the work took longer than 5 hours, subtract half an hour
    # Also if the work overlaps midday.
    if duration > 5 or (duration > 4 and starttime.hour < 12):
        duration -= 0.5

    weeklist = proj_weekdata.setdefault((opdrachtnr, weeknr), {})
    weeklist.setdefault(daynr, []).append(duration)



# Now we have all weekdata in the week. Write them into the database, overwriting the old table.
tasks['Uren'].clear()
names, types = tasks.__annotations__['Uren']
for (opdrachtnr, weeknr), days in proj_weekdata.items():
    parts = [str(weeknr), str(opdrachtnr)]
    for day in range(1, 8):
        parts.append(str(sum(days.get(day, []))))

    tasks['Uren'].append(dataline.create_instance(names, types, parts))

print ('Done!')