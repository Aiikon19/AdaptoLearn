from pathlib import Path

import bcrypt
from test_security import activate

from database import db
from institutions import ADMIN_EMAIL
from seed_service import seed_test_admins
from test_users import TEST_USERS
from tests_helpers import registration, send


def test_test_admin_seed_idempotent_and_immediate_login(app):
    with app.app_context():
        assert seed_test_admins() == 1
        before = dict(db().execute("SELECT * FROM users").fetchone())
        assert seed_test_admins() == 1
        after = dict(db().execute("SELECT * FROM users").fetchone())
        assert before == after
        assert bcrypt.checkpw(TEST_USERS[0]["password"].encode(), after["password"].encode())
        assert (
            after["email_verified"] == 1
            and after["status"] == "ACTIVE"
            and not after["must_reset_password"]
        )
    c = app.test_client()
    response = send(
        c,
        "login",
        data={"email": ADMIN_EMAIL, "password": TEST_USERS[0]["password"], "role": "admin"},
    )
    assert response.status_code == 200 and response.json["redirect"] == "/admin/overview"


def test_wrong_role_wrong_password_and_missing_user_are_generic(app):
    with app.app_context():
        seed_test_admins()
    c = app.test_client()
    payloads = [
        {"email": ADMIN_EMAIL, "password": TEST_USERS[0]["password"], "role": "student"},
        {"email": ADMIN_EMAIL, "password": "wrong", "role": "admin"},
        {"email": "missing@dut4life.ac.za", "password": "wrong", "role": "student"},
    ]
    results = [send(c, "login", data=p) for p in payloads]
    assert all(
        r.status_code == 401 and r.json["error"] == "Invalid email or password" for r in results
    )


def test_registration_reserves_admin_email_and_rejects_admin_role(app):
    c = app.test_client()
    response = send(c, "register", data=registration(email=ADMIN_EMAIL))
    assert (
        response.status_code == 400
        and response.json["error"] == "This email cannot be used for registration"
    )
    assert send(c, "register", data={**registration(), "role": "admin"}).status_code == 400
    with app.app_context():
        assert db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_student_and_admin_redirects_and_guards(app):
    c = app.test_client()
    activate(c, app)
    send(c, "logout")
    result = send(
        c,
        "login",
        data={
            "email": registration()["email"],
            "password": registration()["password"],
            "role": "student",
        },
    )
    assert result.json["redirect"] == "/" and c.get("/api/admin/overview").status_code == 403
    assert send(c, "admin/admins", data={}).status_code == 405


def test_test_credentials_are_not_in_public_assets():
    for root in [Path("static"), Path("templates")]:
        for file in root.rglob("*"):
            if file.is_file() and file.suffix in [".js", ".css", ".html"]:
                assert TEST_USERS[0]["password"] not in file.read_text(encoding="utf-8")
