"""Idempotent additive upgrade. Down: restore manage.py's pre-upgrade backup."""

import sqlite3

from institutions import INSTITUTIONS


def upgrade(connection: sqlite3.Connection) -> None:
    additions = {
        "institutions": {
            "student_email_domain": "TEXT NOT NULL DEFAULT ''",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
        },
        "users": {
            "email_verified": "INTEGER NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION'",
            "admin_level": "TEXT NOT NULL DEFAULT 'admin'",
            "must_reset_password": "INTEGER NOT NULL DEFAULT 0",
            "auth_version": "INTEGER NOT NULL DEFAULT 0",
            "created": "TEXT NOT NULL DEFAULT ''",
        },
    }
    with connection:
        for table, columns in additions.items():
            existing = {r[1] for r in connection.execute(f"PRAGMA table_info({table})")}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        for i in INSTITUTIONS:
            connection.execute(
                "INSERT OR IGNORE INTO institutions(id,name,acronym,student_email_domain,is_active) VALUES(?,?,?,?,?)",
                (i["id"], i["name"], i["shortName"], i["studentEmailDomain"], int(i["isActive"])),
            )
            connection.execute(
                "UPDATE institutions SET student_email_domain=? WHERE id=? AND student_email_domain=''",
                (i["studentEmailDomain"], i["id"]),
            )
        connection.execute(
            "UPDATE users SET created=strftime('%Y-%m-%dT%H:%M:%S+00:00','now') WHERE created=''"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS verification_codes(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),code_hash TEXT NOT NULL,expires_at REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,consumed_at REAL,created REAL NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS rate_limits(id INTEGER PRIMARY KEY,scope TEXT NOT NULL,key TEXT NOT NULL,created REAL NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS password_reset_codes(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),code_hash TEXT NOT NULL,expires_at REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,consumed_at REAL,created REAL NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS rate_lookup ON rate_limits(scope,key,created)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY,actor_id INTEGER,actor_name TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,created TEXT NOT NULL,details TEXT NOT NULL DEFAULT '{}')"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY,actor_id INTEGER REFERENCES users(id),title TEXT NOT NULL,body TEXT NOT NULL,institution_id INTEGER REFERENCES institutions(id),send_at REAL NOT NULL,sent_at REAL,created TEXT NOT NULL)"
        )
