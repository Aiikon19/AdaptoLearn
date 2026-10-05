import sqlite3
import time

import bcrypt
from test_security import activate, admin_client, code

from institutions import ADMIN_EMAIL
from tests_helpers import send

EMAIL = "221234567@dut4life.ac.za"


def test_password_recovery_changes_password_and_invalidates_session(app):
    signed = app.test_client()
    activate(signed, app)
    anon = app.test_client()
    result = send(anon, "auth/forgot-password", data={"email": EMAIL})
    assert result.status_code == 200
    reset_code = code(app)
    with sqlite3.connect(app.config["DATABASE"]) as c:
        hashed = c.execute("SELECT code_hash FROM password_reset_codes").fetchone()[0]
        assert bcrypt.checkpw(reset_code.encode(), hashed.encode())
    assert (
        send(
            anon,
            "auth/recover-password",
            data={"email": EMAIL, "code": reset_code, "password": "NewStudentPassword123"},
        ).status_code
        == 200
    )
    assert signed.get("/api/peers").status_code == 401
    assert (
        send(anon, "login", data={"email": EMAIL, "password": "StudentPassword123"}).status_code
        == 401
    )
    assert (
        send(anon, "login", data={"email": EMAIL, "password": "NewStudentPassword123"}).status_code
        == 200
    )
    assert (
        send(
            anon,
            "auth/recover-password",
            data={"email": EMAIL, "code": reset_code, "password": "AnotherPassword123"},
        ).status_code
        == 400
    )


def test_recovery_request_does_not_reveal_accounts(app):
    signed = app.test_client()
    activate(signed, app)
    c = app.test_client()
    known = send(c, "auth/forgot-password", data={"email": EMAIL})
    unknown = send(c, "auth/forgot-password", data={"email": "missing@dut4life.ac.za"})
    assert known.status_code == unknown.status_code == 200 and known.json == unknown.json


def test_recovery_expiry_attempt_limits_and_resend(app):
    c = app.test_client()
    activate(c, app)
    send(c, "auth/forgot-password", data={"email": EMAIL})
    correct = code(app)
    wrong = "999999" if correct != "999999" else "888888"
    for _ in range(5):
        assert (
            send(
                c,
                "auth/recover-password",
                data={"email": EMAIL, "code": wrong, "password": "NewStudentPassword123"},
            ).json["error"]
            == "Invalid or expired code"
        )
    assert (
        send(
            c,
            "auth/recover-password",
            data={"email": EMAIL, "code": correct, "password": "NewStudentPassword123"},
        ).status_code
        == 400
    )
    assert send(c, "auth/forgot-password", data={"email": EMAIL}).status_code == 429
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        connection.execute("DELETE FROM rate_limits WHERE scope='recovery-email'")
    assert send(c, "auth/forgot-password", data={"email": EMAIL}).status_code == 200
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM password_reset_codes WHERE consumed_at IS NULL"
            ).fetchone()[0]
            == 1
        )
        connection.execute("UPDATE password_reset_codes SET expires_at=?", (time.time() - 1,))
    assert (
        send(
            c,
            "auth/recover-password",
            data={"email": EMAIL, "code": code(app), "password": "NewStudentPassword123"},
        ).status_code
        == 400
    )


def test_recovery_preserves_admin_role(app):
    old = admin_client(app)
    c = app.test_client()
    send(c, "auth/forgot-password", data={"email": ADMIN_EMAIL})
    assert (
        send(
            c,
            "auth/recover-password",
            data={"email": ADMIN_EMAIL, "code": code(app), "password": "RecoveredAdminPassword123"},
        ).status_code
        == 200
    )
    assert old.get("/api/admin/overview").status_code == 401
    response = send(
        c,
        "login",
        data={"email": ADMIN_EMAIL, "role": "admin", "password": "RecoveredAdminPassword123"},
    )
    assert response.json["redirect"] == "/admin/overview"


def test_recovery_requires_csrf_and_valid_input(app):
    c = app.test_client()
    assert c.post("/api/auth/forgot-password", json={"email": EMAIL}).status_code == 400
    assert send(c, "auth/forgot-password", data={"email": "bad"}).status_code == 400
    assert (
        send(
            c, "auth/recover-password", data={"email": EMAIL, "code": "123456", "password": "short"}
        ).status_code
        == 400
    )


def test_failed_delivery_returns_generic_response_and_rolls_back_code(app):
    c = app.test_client()
    activate(c, app)
    from errors import AppError

    def fail(_):
        raise AppError("Delivery failed", 503)

    app.config["TEST_MAILER"] = fail
    result = send(c, "auth/forgot-password", data={"email": EMAIL})
    assert result.status_code == 200
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM password_reset_codes").fetchone()[0] == 0
