
from dataclasses import dataclass
from admingen.data.sqlite_db import SqliteDatabase


if __name__ == "__main__":

    @dataclass
    class MyTable:
        id: int
        name: str

    db = SqliteDatabase('test.sql', [MyTable])
