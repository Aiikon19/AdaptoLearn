from functools import wraps

from flask import g, redirect, request, session

from database import db
from errors import AppError


def current_user() -> dict | None:
    row = (
        db()
        .execute(
            "SELECT * FROM users WHERE id=? AND active=1 AND status='ACTIVE' AND email_verified=1 AND must_reset_password=0",
            (session.get("uid"),),
        )
        .fetchone()
    )
    if not row or session.get("version") != row["auth_version"]:
        return None
    return dict(row)


def establish_session(user: dict) -> None:
    import secrets

    session.clear()
    session["uid"] = user["id"]
    session["version"] = user["auth_version"]
    session["csrf"] = secrets.token_hex(24)


def student_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            raise AppError("Please sign in to continue.", 401)
        if user["role"] != "student":
            raise AppError("Student access required.", 403)
        g.user = user
        return fn(*args, **kwargs)

    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            if not request.path.startswith("/api/"):
                return redirect("/?login=1")
            raise AppError("Please sign in to continue.", 401)
        if user["role"] != "admin":
            raise AppError("Administrator access required.", 403)
        g.user = user
        return fn(*args, **kwargs)

    return wrapped
