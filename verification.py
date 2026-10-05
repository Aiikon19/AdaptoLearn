import secrets
import time

import bcrypt

from database import db, transaction
from errors import AppError
from mailer import send_verification
from validation import validate_student_email

TTL = 900
MAX_ATTEMPTS = 5
COOLDOWN = 60


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def limit(scope: str, key: str, maximum: int, window: int) -> None:
    stamp = time.time()
    with transaction() as c:
        c.execute("DELETE FROM rate_limits WHERE created<?", (stamp - 3600,))
        count = c.execute(
            "SELECT COUNT(*) FROM rate_limits WHERE scope=? AND key=? AND created>?",
            (scope, key, stamp - window),
        ).fetchone()[0]
        if count >= maximum:
            raise AppError("Too many requests. Please try again later.", 429)
        c.execute("INSERT INTO rate_limits(scope,key,created) VALUES(?,?,?)", (scope, key, stamp))


def endpoint_limits(action: str, ip: str, uid: int | None) -> None:
    limit(action + "-ip", ip, 30, 600)
    if uid is not None:
        limit(action + "-user", str(uid), 15, 600)


def issue_code(uid: int, resend: bool = False) -> None:
    with transaction() as c:
        user = c.execute(
            "SELECT u.*,i.name institution,i.is_active,i.student_email_domain FROM users u JOIN institutions i ON i.id=u.institution_id WHERE u.id=?",
            (uid,),
        ).fetchone()
        if (
            not user
            or user["role"] != "student"
            or user["status"] != "PENDING_VERIFICATION"
            or not user["active"]
        ):
            raise AppError("Unable to send a code for this account.")
        validate_student_email(user["email"], user)
        stamp = time.time()
        previous = c.execute(
            "SELECT created FROM verification_codes WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (uid,),
        ).fetchone()
        if previous and stamp - previous["created"] < COOLDOWN:
            raise AppError("Please wait 60 seconds before requesting another code.", 429)
        if resend:
            limit("resend-hour", str(uid), 5, 3600)
        code = generate_code()
        hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
        c.execute(
            "UPDATE verification_codes SET consumed_at=? WHERE user_id=? AND consumed_at IS NULL",
            (stamp, uid),
        )
        c.execute(
            "INSERT INTO verification_codes(user_id,code_hash,expires_at,created) VALUES(?,?,?,?)",
            (uid, hashed, stamp + TTL, stamp),
        )
        send_verification(user["email"], user["institution"], code)


def verify_code(uid: int, code: str) -> dict:
    succeeded = False
    with transaction() as c:
        user = c.execute(
            "SELECT u.*,i.is_active,i.student_email_domain FROM users u JOIN institutions i ON i.id=u.institution_id WHERE u.id=?",
            (uid,),
        ).fetchone()
        record = c.execute(
            "SELECT * FROM verification_codes WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)
        ).fetchone()
        stamp = time.time()
        valid_user = (
            user
            and user["role"] == "student"
            and user["status"] == "PENDING_VERIFICATION"
            and user["active"]
            and user["is_active"]
            and user["email"].endswith("@" + user["student_email_domain"])
        )
        if record and record["consumed_at"] is None and record["attempts"] < MAX_ATTEMPTS:
            c.execute(
                "UPDATE verification_codes SET attempts=attempts+1 WHERE id=?", (record["id"],)
            )
            if (
                valid_user
                and record["expires_at"] > stamp
                and len(code) == 6
                and code.isascii()
                and code.isdigit()
                and bcrypt.checkpw(code.encode(), record["code_hash"].encode())
            ):
                c.execute(
                    "UPDATE users SET email_verified=1,status='ACTIVE',auth_version=auth_version+1 WHERE id=?",
                    (uid,),
                )
                c.execute(
                    "UPDATE verification_codes SET consumed_at=? WHERE user_id=? AND consumed_at IS NULL",
                    (stamp, uid),
                )
                succeeded = True
    if not succeeded:
        raise AppError("Invalid or expired code", 400, "code")
    return dict(db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
