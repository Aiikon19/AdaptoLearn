import re
import sqlite3
import time

import pytest

from database import db
from errors import AppError
from institutions import ADMIN_EMAIL, INSTITUTIONS
from maintenance import DEMO_EMAILS, cleanup_demo, setup_admin
from migrations import upgrade
from tests_helpers import registration, send
from verification import generate_code


def code(app, index=-1):
    return re.search(
        r"code is: ([0-9]{6})",
        app.extensions["mailbox"][index].get_body(preferencelist=("plain",)).get_content(),
    ).group(1)


def change(app, sql, args=()):
    with sqlite3.connect(app.config["DATABASE"]) as c:
        c.execute(sql, args)


def activate(client, app):
    assert send(client, "register", data=registration()).status_code == 201
    assert send(client, "verify", data={"code": code(app)}).status_code == 200


def admin_client(app, super_admin=True):
    with app.app_context():
        setup_admin(db(), "InitialAdminPassword123")
    client = app.test_client()
    result = send(
        client,
        "login",
        data={"email": ADMIN_EMAIL, "role": "admin", "password": "InitialAdminPassword123"},
    )
    assert result.json["resetRequired"]
    assert (
        send(
            client, "auth/reset-password", data={"password": "ChangedAdminPassword123"}
        ).status_code
        == 200
    )
    if not super_admin:
        change(app, "UPDATE users SET admin_level='admin' WHERE role='admin'")
    return client


def test_registry_unique_stable_and_exact():
    assert len(INSTITUTIONS) == 26
    assert len({i["id"] for i in INSTITUTIONS}) == 26
    assert (
        next(i for i in INSTITUTIONS if i["shortName"] == "DUT")["studentEmailDomain"]
        == "dut4life.ac.za"
    )
    assert ADMIN_EMAIL == "22445780@dut4life.ac.za"


def test_student_cannot_switch_to_another_institution_domain(app):
    c = app.test_client()
    activate(c, app)
    data = {
        "name": "Student",
        "institution_id": 20,
        "programme": "BSc",
        "year": 2,
        "skills": [],
        "needs": [],
        "modules": [],
        "preferences": [],
        "interests": [],
        "availability": [],
    }
    assert send(c, "profile", "PUT", data).status_code == 400
    assert c.get("/api/bootstrap").json["user"]["institution_id"] == 3


@pytest.mark.parametrize(
    "email",
    [
        "student@gmail.com",
        "student@yahoo.com",
        "student@outlook.com",
        "student@uj.ac.za",
        "student@sub.dut4life.ac.za",
        "student@dut4life.ac.za.evil",
        "invalid space@dut4life.ac.za",
    ],
)
def test_wrong_domains_rejected_server_side(app, email):
    client = app.test_client()
    r = send(client, "register", data=registration(email=email))
    assert r.status_code == 400 and r.json["field"] == "email"


def test_normalized_email_and_pending_has_no_access(app):
    client = app.test_client()
    assert (
        send(client, "register", data=registration(email=" 221ABC@DUT4LIFE.AC.ZA ")).status_code
        == 201
    )
    assert client.get("/api/bootstrap").json["pendingEmail"] == "221abc@dut4life.ac.za"
    assert client.get("/api/peers").status_code == 401
    result = send(
        client, "login", data={"email": "221abc@dut4life.ac.za", "password": "StudentPassword123"}
    )
    assert result.json["pendingVerification"] and client.get("/api/activity").status_code == 401
    with app.app_context():
        u = db().execute("SELECT * FROM users").fetchone()
        assert u["email_verified"] == 0 and u["status"] == "PENDING_VERIFICATION"
        record = db().execute("SELECT * FROM verification_codes").fetchone()
        assert record["code_hash"].startswith("$2b$") and code(app) not in record["code_hash"]
        assert 890 < record["expires_at"] - time.time() <= 900
    assert (
        "Do not share"
        in app.extensions["mailbox"][0].get_body(preferencelist=("plain",)).get_content()
    )
    assert (
        "Durban University of Technology"
        in app.extensions["mailbox"][0].get_body(preferencelist=("plain",)).get_content()
    )


def test_code_is_six_digits_and_uses_csprng(monkeypatch):
    monkeypatch.setattr("verification.secrets.randbelow", lambda _: 7)
    assert generate_code() == "000007"


def test_success_consumes_all_codes_and_single_use(app):
    c = app.test_client()
    activate(c, app)
    assert c.get("/api/peers").status_code == 200
    with app.app_context():
        assert (
            db()
            .execute("SELECT COUNT(*) FROM verification_codes WHERE consumed_at IS NULL")
            .fetchone()[0]
            == 0
        )
    assert send(c, "verify", data={"code": code(app)}).status_code == 400


def test_attempt_limit_and_generic_error(app):
    c = app.test_client()
    send(c, "register", data=registration())
    correct = code(app)
    wrong = "999999" if correct != "999999" else "888888"
    for _ in range(5):
        r = send(c, "verify", data={"code": wrong})
        assert r.status_code == 400 and r.json["error"] == "Invalid or expired code"
    assert send(c, "verify", data={"code": correct}).json["error"] == "Invalid or expired code"
    with app.app_context():
        assert db().execute("SELECT attempts FROM verification_codes").fetchone()[0] == 5


def test_malformed_code_counts_as_attempt(app):
    c = app.test_client()
    send(c, "register", data=registration())
    assert send(c, "verify", data={"code": "a"}).status_code == 400
    with app.app_context():
        assert db().execute("SELECT attempts FROM verification_codes").fetchone()[0] == 1


def test_expiry_and_resend_invalidation_cooldown_hour_limit(app):
    c = app.test_client()
    send(c, "register", data=registration())
    old = code(app)
    change(app, "UPDATE verification_codes SET expires_at=?", (time.time() - 1,))
    assert send(c, "verify", data={"code": old}).json["error"] == "Invalid or expired code"
    assert send(c, "verification/resend").status_code == 429
    for _ in range(5):
        change(app, "UPDATE verification_codes SET created=?", (time.time() - 61,))
        assert send(c, "verification/resend").status_code == 200
    change(app, "UPDATE verification_codes SET created=?", (time.time() - 61,))
    assert send(c, "verification/resend").status_code == 429
    with app.app_context():
        assert (
            db()
            .execute("SELECT COUNT(*) FROM verification_codes WHERE consumed_at IS NULL")
            .fetchone()[0]
            == 1
        )


def test_user_and_ip_rate_limits(app):
    c = app.test_client()
    send(c, "register", data=registration())
    for _ in range(15):
        send(c, "verify", data={"code": "wrong"})
    assert send(c, "verify", data={"code": "wrong"}).status_code == 429
    anon = app.test_client()
    for _ in range(15):
        send(anon, "verify", data={"code": "wrong"})
    assert send(anon, "verify", data={"code": "wrong"}).status_code == 429


def test_mail_failure_rolls_back_account_and_code(app):
    def failure(_):
        raise AppError("Email unavailable", 503)

    app.config["TEST_MAILER"] = failure
    c = app.test_client()
    assert send(c, "register", data=registration()).status_code == 503
    with app.app_context():
        assert db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert db().execute("SELECT COUNT(*) FROM verification_codes").fetchone()[0] == 0


def test_admin_initial_reset_required_email_and_idempotency(app):
    with app.app_context():
        uid = setup_admin(db(), "InitialAdminPassword123")
        assert setup_admin(db(), "DifferentPassword123") == uid
    c = app.test_client()
    assert send(
        c,
        "login",
        data={"email": ADMIN_EMAIL, "role": "admin", "password": "InitialAdminPassword123"},
    ).json["resetRequired"]
    assert c.get("/api/admin/overview").status_code == 401
    assert (
        send(c, "auth/reset-password", data={"password": "InitialAdminPassword123"}).status_code
        == 400
    )
    assert (
        send(c, "auth/reset-password", data={"password": "ChangedAdminPassword123"}).status_code
        == 200
    )
    assert c.get("/api/admin/overview").status_code == 200
    assert c.get("/api/peers").status_code == 403


def test_admin_management_student_controls_and_audit(app):
    c = app.test_client()
    activate(c, app)
    a = admin_client(app)
    uid = c.get("/api/bootstrap").json["user"]["id"]
    assert a.get("/api/admin/overview").json["verifiedStudents"] == 1
    recent = a.get("/api/admin/overview").json["recentSignups"][0]
    assert (
        recent["email_verified"] == 1
        and recent["active"] == 1
        and recent["institution"] == "Durban University of Technology"
    )
    assert send(a, f"admin/students/{uid}", data={"action": "unverify"}).status_code == 200
    assert c.get("/api/peers").status_code == 401
    assert send(a, f"admin/students/{uid}", data={"action": "resend"}).status_code == 429
    assert send(a, f"admin/students/{uid}", data={"action": "verify"}).status_code == 200
    assert send(a, f"admin/students/{uid}", data={"action": "suspend"}).status_code == 200
    assert send(a, f"admin/students/{uid}", data={"action": "reactivate"}).status_code == 200
    assert a.get("/api/admin/students?q=221&institution=3&status=ACTIVE").json["users"]
    assert send(a, f"admin/students/{uid}", data={"action": "delete"}).status_code == 200
    assert a.get(f"/api/admin/students/{uid}").status_code == 404
    assert len(a.get("/api/admin/audit").json["entries"]) >= 6


def test_institution_admin_changes_flow_to_signup(app):
    a = admin_client(app)
    assert (
        send(
            a,
            "admin/institutions/3",
            "PUT",
            {"studentEmailDomain": "students.dut.ac.za", "isActive": True},
        ).status_code
        == 200
    )
    c = app.test_client()
    assert send(c, "register", data=registration()).status_code == 400
    assert send(c, "register", data=registration(email="221@students.dut.ac.za")).status_code == 201
    assert (
        send(
            a,
            "admin/institutions/3",
            "PUT",
            {"studentEmailDomain": "students.dut.ac.za", "isActive": False},
        ).status_code
        == 200
    )
    assert (
        send(
            app.test_client(), "register", data=registration(email="222@students.dut.ac.za")
        ).status_code
        == 400
    )
    assert send(c, "verify", data={"code": code(app)}).status_code == 400


def test_super_admin_controls_roles_and_revokes_sessions(app):
    a = admin_client(app)
    assert (
        send(
            a,
            "admin/admins",
            data={
                "name": "Operator",
                "email": "operator@dut4life.ac.za",
                "password": "InitialOperatorPassword",
                "adminLevel": "admin",
            },
        ).status_code
        == 405
    )
    from werkzeug.security import generate_password_hash

    change(
        app,
        "INSERT INTO users(name,email,password,institution_id,programme,year,role,email_verified,status,admin_level,must_reset_password,created) VALUES('Operator','operator@dut4life.ac.za',?,3,'Administration',1,'admin',1,'ACTIVE','admin',1,'2026-10-04')",
        (generate_password_hash("InitialOperatorPassword"),),
    )
    uid = a.get("/api/admin/admins").json["users"][-1]["id"]
    b = app.test_client()
    send(
        b,
        "login",
        data={
            "email": "operator@dut4life.ac.za",
            "role": "admin",
            "password": "InitialOperatorPassword",
        },
    )
    send(b, "auth/reset-password", data={"password": "ChangedOperatorPassword"})
    assert b.get("/api/admin/admins").status_code == 403
    assert (
        send(a, f"admin/admins/{uid}", "PUT", {"active": False, "adminLevel": "admin"}).status_code
        == 200
    )
    assert b.get("/api/admin/overview").status_code == 401
    self_id = a.get("/api/bootstrap").json["user"]["id"]
    assert (
        send(
            a, f"admin/admins/{self_id}", "PUT", {"active": False, "adminLevel": "admin"}
        ).status_code
        == 400
    )


def test_announcements_now_scheduled_and_audience(app):
    c = app.test_client()
    activate(c, app)
    a = admin_client(app)
    assert (
        send(
            a,
            "admin/announcements",
            data={"title": "Welcome", "body": "Study safely", "institution_id": 3, "send_at": None},
        ).status_code
        == 201
    )
    assert any(
        n["message"] == "Welcome\nStudy safely"
        for n in c.get("/api/activity").json["notifications"]
    )
    assert (
        send(
            a,
            "admin/announcements",
            data={
                "title": "Future",
                "body": "Next week",
                "institution_id": None,
                "send_at": "2099-01-01T12:00:00+02:00",
            },
        ).status_code
        == 201
    )
    from admin_service import dispatch_announcements

    with app.app_context():
        assert dispatch_announcements() == 0
        db().execute("UPDATE announcements SET send_at=0 WHERE sent_at IS NULL")
        db().commit()
        assert dispatch_announcements() == 1
        assert dispatch_announcements() == 0


def test_cleanup_idempotent_preserves_real_users_reference_data(app):
    c = app.test_client()
    activate(c, app)
    with app.app_context():
        connection = db()
        real = connection.execute("SELECT id FROM users").fetchone()[0]
        for email in DEMO_EMAILS:
            connection.execute(
                "INSERT INTO users(name,email,password,institution_id,programme,year) VALUES('Former seed',?,'unused',3,'BSc',1)",
                (email,),
            )
        seed = connection.execute(
            "SELECT id FROM users WHERE email=?", (DEMO_EMAILS[0],)
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO study_sessions(creator,peer,module,topic,starts,duration,location) VALUES(?,?,'Computer Science','Removed session','2020-01-01T12:00',60,'Library')",
            (seed, real),
        )
        connection.commit()
        assert cleanup_demo(connection) == 6 and cleanup_demo(connection) == 0
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM institutions").fetchone()[0] == 26
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        upgrade(connection)
        upgrade(connection)
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
