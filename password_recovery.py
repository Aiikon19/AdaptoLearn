"""Rate-limited password recovery; requesting a code never reveals an account."""

import logging
import time

import bcrypt
from werkzeug.security import generate_password_hash

from database import db, transaction
from errors import AppError
from mailer import send_password_reset
from verification import MAX_ATTEMPTS, TTL, generate_code, limit

REQUEST_MESSAGE = (
    "If an eligible account exists, a password reset code has been sent to its email address."
)


def request_reset(email: str, ip: str) -> None:
    email = email.strip().lower()
    limit("recovery-ip", ip, 20, 3600)
    limit("recovery-email", email, 1, 60)
    limit("recovery-hour", email, 5, 3600)
    user = (
        db()
        .execute(
            "SELECT * FROM users WHERE email=? AND active=1 AND email_verified=1 AND status='ACTIVE'",
            (email,),
        )
        .fetchone()
    )
    if not user:
        return
    try:
        with transaction() as c:
            code = generate_code()
            stamp = time.time()
            hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
            c.execute(
                "UPDATE password_reset_codes SET consumed_at=? WHERE user_id=? AND consumed_at IS NULL",
                (stamp, user["id"]),
            )
            c.execute(
                "INSERT INTO password_reset_codes(user_id,code_hash,expires_at,created) VALUES(?,?,?,?)",
                (user["id"], hashed, stamp + TTL, stamp),
            )
            send_password_reset(email, code)
    except AppError:
        # Same response for missing accounts and delivery failures. No credentials logged.
        logging.getLogger(__name__).warning("Password recovery email could not be sent.")


def complete_reset(email: str, code: str, password: str, ip: str) -> None:
    email = email.strip().lower()
    limit("recovery-complete-ip", ip, 30, 600)
    limit("recovery-complete-email", email, 15, 600)
    success = False
    with transaction() as c:
        user = c.execute(
            "SELECT * FROM users WHERE email=? AND active=1 AND email_verified=1 AND status='ACTIVE'",
            (email,),
        ).fetchone()
        record = c.execute(
            "SELECT * FROM password_reset_codes WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user["id"] if user else None,),
        ).fetchone()
        stamp = time.time()
        if record and record["consumed_at"] is None and record["attempts"] < MAX_ATTEMPTS:
            c.execute(
                "UPDATE password_reset_codes SET attempts=attempts+1 WHERE id=?", (record["id"],)
            )
            if (
                record["expires_at"] > stamp
                and len(code) == 6
                and code.isascii()
                and code.isdigit()
                and bcrypt.checkpw(code.encode(), record["code_hash"].encode())
            ):
                c.execute(
                    "UPDATE users SET password=?,must_reset_password=0,auth_version=auth_version+1 WHERE id=?",
                    (generate_password_hash(password), user["id"]),
                )
                c.execute(
                    "UPDATE password_reset_codes SET consumed_at=? WHERE user_id=? AND consumed_at IS NULL",
                    (stamp, user["id"]),
                )
                success = True
    if not success:
        raise AppError("Invalid or expired code", 400, "code")
