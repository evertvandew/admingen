
import datetime
from croniter import croniter
from dataclasses import dataclass


# TODO: 1). create a reminder service for existing LCX plannings.
# TODO: 2). create a webinterface for this service.
# TODO: 3). let the thing create a planning for a next month / quarter.


# Define the database elements

@dataclass
class User:
    name: str
    full_name: str
    planning_uri: str
    reminder_uri: str

@dataclass
class Task:
    name: str
    description: str
    nr_required: int
    duration: str       # e.g. 1(s), 2.5d, 3h, 5mi
    activation: str     # cron-like activation string

@dataclass
class UserTask:
    user: User
    team: Task

@dataclass
class Exclusions:
    task1: Task
    task2: Task

@dataclass
class Planning:
    task: Task
    activation: datetime
    user: User
    nr: int


def create_triggers(task_schedules, start, end):
    """ Returns a dictionary of tasks : trigger moments. """
    triggers = {}
    for ts in task_schedules:
        task = ts.task
        tt = triggers.setdefault(task.id, [])
        for trigger in croniter(ts.activation, start, ret_type=datetime.datetime):
            if trigger > end:
                break
            tt.append(trigger)
    return triggers


def send_reminders(data):
    # Find planned activities between 2 and 3 days from now
    # And send reminders, if configured to do so.
    now = datetime.datetime.now()
    now = datetime.datetime(now.year, now.month, now.day)
    for planning in data['Planning']:
        d = planning.activation - now
        if datetime.timedelta(2) <= d <= datetime.timedelta(3):
            # Send the reminder




if __name__ == '__main__':
    task = Task(1, None, 'Test taak')
    ts = Planning(1, task, '30min', '45 10 * * 0')

    print(create_triggers([ts], datetime.datetime.now(), datetime.datetime(2019, 4, 1)))
