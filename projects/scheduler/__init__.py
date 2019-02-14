





# Define the database elements

class User:
    pass

class Team:
    pass

class UserTeam:
    user: User
    team: Team

class Task:
    team: Team
    description: str

class TaskSchedule:
    task: Task
    duration: str
    activation: str

class UserTask:
    user: User
    task: Task

