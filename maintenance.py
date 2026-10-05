"""Scoped data maintenance used by both CLI and administrator services."""

import sqlite3
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from errors import AppError
from institutions import ADMIN_EMAIL, DUT_ID

DEMO_EMAILS = (
    "learner@demo.local",
    "peer1@demo.local",
    "peer2@demo.local",
    "peer3@demo.local",
    "peer4@demo.local",
    "peer5@demo.local",
)


def delete_user_records(c: sqlite3.Connection, uid: int) -> None:
    c.execute(
        "DELETE FROM feedback WHERE author=? OR session_id IN (SELECT id FROM study_sessions WHERE creator=? OR peer=?)",
        (uid, uid, uid),
    )
    c.execute("DELETE FROM study_sessions WHERE creator=? OR peer=?", (uid, uid))
    c.execute("DELETE FROM connections WHERE sender=? OR receiver=?", (uid, uid))
    c.execute("DELETE FROM matches WHERE user_id=? OR peer_id=?", (uid, uid))
    c.execute("DELETE FROM notifications WHERE user_id=?", (uid,))
    c.execute("DELETE FROM verification_codes WHERE user_id=?", (uid,))
    c.execute("DELETE FROM password_reset_codes WHERE user_id=?", (uid,))
    c.execute(
        "DELETE FROM rate_limits WHERE key=? AND scope IN ('verify-user','resend-user','resend-hour')",
        (str(uid),),
    )
    c.execute("DELETE FROM login_attempts WHERE email=(SELECT email FROM users WHERE id=?)", (uid,))
    c.execute("DELETE FROM rate_limits WHERE key=(SELECT email FROM users WHERE id=?)", (uid,))
    c.execute("UPDATE announcements SET actor_id=NULL WHERE actor_id=?", (uid,))
    c.execute("DELETE FROM users WHERE id=?", (uid,))


def cleanup_demo(c: sqlite3.Connection) -> int:
    targets = c.execute("SELECT id FROM users WHERE email IN (?,?,?,?,?,?)", DEMO_EMAILS).fetchall()
    with c:
        for user in targets:
            delete_user_records(c, user[0])
    return len(targets)


def setup_admin(c: sqlite3.Connection, password: str, old_email: str | None = None) -> int:
    if not 10 <= len(password) <= 128:
        raise AppError("ADMIN_INITIAL_PASSWORD must contain 10–128 characters.")
    target = c.execute("SELECT * FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone()
    if target:
        if target["role"] != "admin":
            raise AppError("The target address belongs to a student. No changes made.", 409)
        return target["id"]
    admins = c.execute(
        "SELECT * FROM users WHERE role='admin'" + (" AND email=?" if old_email else ""),
        (old_email,) if old_email else (),
    ).fetchall()
    if len(admins) > 1:
        raise AppError("Set ADMIN_OLD_EMAIL to select the administrator to migrate.")
    if old_email and not admins:
        raise AppError("ADMIN_OLD_EMAIL does not identify an administrator.")
    stamp = datetime.now(timezone.utc).isoformat()
    with c:
        if admins:
            uid = admins[0]["id"]
            c.execute(
                "UPDATE users SET email=?,password=?,institution_id=?,email_verified=1,status='ACTIVE',active=1,admin_level='super-admin',must_reset_password=1,auth_version=auth_version+1 WHERE id=?",
                (ADMIN_EMAIL, generate_password_hash(password), DUT_ID, uid),
            )
        else:
            uid = c.execute(
                "INSERT INTO users(name,email,password,institution_id,programme,year,role,email_verified,status,admin_level,must_reset_password,created) VALUES(?,?,?,?,?,1,'admin',1,'ACTIVE','super-admin',1,?)",
                (
                    "Administrator",
                    ADMIN_EMAIL,
                    generate_password_hash(password),
                    DUT_ID,
                    "Administration",
                    stamp,
                ),
            ).lastrowid
        c.execute(
            "INSERT INTO audit_log(actor_name,action,target,created) VALUES(?,?,?,?)",
            ("Maintenance CLI", "admin.email-migration", str(uid), stamp),
        )
    return uid
