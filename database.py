import sqlite3
from contextlib import contextmanager
from typing import Generator

from flask import current_app, g


def db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@contextmanager
def transaction() -> Generator[sqlite3.Connection, None, None]:
    connection = db()
    if connection.in_transaction:
        yield connection
        return
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def execute(sql: str, args: tuple = ()) -> sqlite3.Cursor:
    connection = db()
    nested = connection.in_transaction
    cursor = connection.execute(sql, args)
    if not nested:
        connection.commit()
    return cursor


def rows(sql: str, args: tuple = ()) -> list[dict]:
    return [dict(row) for row in db().execute(sql, args).fetchall()]
