import sqlite3
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from database import db, transaction
from errors import AppError
from institutions import ADMIN_EMAIL
from password_hashing import password_matches
from validation import validate_student_email
from verification import issue_code, limit


def register_student(data: dict, ip: str) -> int:
    limit("registration-ip", ip, 15, 3600)
    candidate = data["email"].strip().lower()
    existing = db().execute("SELECT role FROM users WHERE email=?", (candidate,)).fetchone()
    if candidate == ADMIN_EMAIL or existing and existing["role"] == "admin":
        raise AppError("This email cannot be used for registration", 400, "email")
    institution = (
        db().execute("SELECT * FROM institutions WHERE id=?", (data["institution_id"],)).fetchone()
    )
    if not institution:
        raise AppError("Select a valid institution.", field="institution_id")
    email = validate_student_email(data["email"], institution)
    if not data["name"].strip() or not data["programme"].strip():
        raise AppError("Name and programme are required.")
    try:
        with transaction() as c:
            uid = c.execute(
                "INSERT INTO users(name,email,password,institution_id,programme,year,created) VALUES(?,?,?,?,?,?,?)",
                (
                    data["name"].strip(),
                    email,
                    generate_password_hash(data["password"]),
                    data["institution_id"],
                    data["programme"].strip(),
                    data["year"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            ).lastrowid
            issue_code(uid)
            return uid
    except sqlite3.IntegrityError:
        raise AppError(
            "An account with this email already exists. Sign in to continue verification.",
            409,
            "email",
        ) from None


def authenticate(email: str, password: str, role: str, ip: str) -> dict:
    email = email.strip().lower()
    limit("login-ip", ip, 30, 900)
    limit("login-user", email, 10, 900)
    user = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if (
        not user
        or not password_matches(user["password"], password)
        or user["role"] != role
        or not user["active"]
        or user["status"] == "SUSPENDED"
    ):
        raise AppError("Invalid email or password", 401)
    return dict(user)


def reset_admin_password(uid: int, password: str) -> dict:
    with transaction() as c:
        user = c.execute(
            "SELECT * FROM users WHERE id=? AND role='admin' AND active=1 AND must_reset_password=1",
            (uid,),
        ).fetchone()
        if not user:
            raise AppError("Password reset is unavailable.", 403)
        if password_matches(user["password"], password):
            raise AppError("Choose a different password.", field="password")
        c.execute(
            "UPDATE users SET password=?,must_reset_password=0,auth_version=auth_version+1 WHERE id=?",
            (generate_password_hash(password), uid),
        )
        c.execute(
            "INSERT INTO audit_log(actor_id,actor_name,action,target,created) VALUES(?,?,?,?,?)",
            (
                uid,
                user["name"],
                "admin.password-reset",
                str(uid),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return dict(db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
