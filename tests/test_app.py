import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    mailbox = []
    result = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(tmp_path / "test.sqlite"),
            "TEST_MAILER": mailbox.append,
        }
    )
    result.extensions["test_mailbox"] = mailbox
    return result


def token(client):
    return {"X-CSRF-Token": client.get("/api/bootstrap").json["csrf"]}


def send(client, path, method="POST", data=None):
    if path == "login" and data and "role" not in data:
        data = {**data, "role": "student"}
    return client.open("/api/" + path, method=method, json=data or {}, headers=token(client))


def register(client, email="alice@uj.ac.za", name="Alice"):
    response = send(
        client,
        "register",
        data={
            "name": name,
            "email": email,
            "password": "StrongPassword123",
            "institution_id": 16,
            "programme": "BSc Computer Science",
            "year": 2,
        },
    )
    if response.status_code == 201:
        import re

        code = re.search(
            r"code is: ([0-9]{6})",
            client.application.extensions["test_mailbox"][-1]
            .get_body(preferencelist=("plain",))
            .get_content(),
        ).group(1)
        assert send(client, "verify", data={"code": code}).status_code == 200
    return response


def change(app, sql, args=()):
    with sqlite3.connect(app.config["DATABASE"]) as c:
        c.execute(sql, args)


def user_profile(**kw):
    return {
        "name": "Alice",
        "programme": "Computer Science",
        "year": 2,
        "institution_id": 16,
        "modules": ["Computer Science"],
        "skills": ["Algorithms"],
        "needs": [{"topic": "Python", "priority": 3}],
        "preferences": ["Online"],
        "interests": ["Music"],
        "availability": [{"day": "Monday", "start": "16:00", "end": "18:00"}],
        **kw,
    }


def pair(app):
    a, b = app.test_client(), app.test_client()
    assert register(a).status_code == 201
    assert register(b, "bob@uj.ac.za", "Bob").status_code == 201
    return a, b


def connected(app):
    a, b = pair(app)
    assert send(a, "connections", data={"peer_id": 2}).status_code == 201
    assert send(b, "connections/1", "PATCH", {"status": "accepted"}).status_code == 200
    return a, b


def invitation(app):
    a, b = connected(app)
    starts = (
        datetime.now(timezone(timedelta(hours=2))).replace(tzinfo=None) + timedelta(days=2)
    ).isoformat(timespec="minutes")
    data = {
        "peer_id": 2,
        "module": "Computer Science",
        "topic": "Python",
        "starts": starts,
        "duration": 60,
        "location": "Library",
    }
    assert send(a, "sessions", data=data).status_code == 201
    return a, b, data


def test_home_bootstrap_health_and_institutions(app):
    c = app.test_client()
    assert c.get("/").status_code == 200
    r = c.get("/api/bootstrap")
    assert len(r.json["institutions"]) == 26
    assert len({i["name"] for i in r.json["institutions"]}) == 26
    assert r.json["user"] is None
    assert c.get("/health").json == {"status": "ok"}
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert c.get("/static/app.js").mimetype == "text/javascript"
    assert c.get("/static/style.css").mimetype == "text/css"


def test_registration_login_logout_password_hash(app):
    c = app.test_client()
    assert register(c).status_code == 201
    assert c.get("/api/bootstrap").json["user"]["name"] == "Alice"
    assert "password" not in c.get("/api/bootstrap").json["user"]
    with sqlite3.connect(app.config["DATABASE"]) as d:
        assert d.execute("SELECT password FROM users").fetchone()[0] != "StrongPassword123"
    assert send(c, "logout").status_code == 200
    assert c.get("/api/peers").status_code == 401
    assert (
        send(c, "login", data={"email": "alice@uj.ac.za", "password": "wrong"}).status_code == 401
    )
    assert (
        send(
            c, "login", data={"email": "alice@uj.ac.za", "password": "StrongPassword123"}
        ).status_code
        == 200
    )


def test_csrf_required_and_rotated(app):
    c = app.test_client()
    old = token(c)
    assert c.post("/api/register", json={}).status_code == 400
    assert register(c).status_code == 201
    assert c.post("/api/logout", headers=old, json={}).status_code == 400


@pytest.mark.parametrize(
    "key,value",
    [("email", "bad"), ("password", "short"), ("institution_id", 27), ("year", 0), ("name", "")],
)
def test_registration_validation(app, key, value):
    c = app.test_client()
    d = {
        "name": "Alice",
        "email": "alice@uj.ac.za",
        "password": "StrongPassword123",
        "institution_id": 16,
        "programme": "BSc",
        "year": 1,
    }
    d[key] = value
    assert send(c, "register", data=d).status_code == 400


def test_duplicate_registration(app):
    pair(app)
    assert register(app.test_client()).status_code == 409


def test_profile_persistence_and_peer_privacy(app):
    a, b = pair(app)
    assert send(a, "profile", "PUT", user_profile()).status_code == 200
    assert a.get("/api/bootstrap").json["user"]["profile"]["needs"][0]["priority"] == 3
    peer = b.get("/api/peers/1").json["user"]
    assert "email" not in peer and "password" not in peer
    restarted = create_app(
        {"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE": app.config["DATABASE"]}
    )
    c = restarted.test_client()
    send(c, "login", data={"email": "alice@uj.ac.za", "password": "StrongPassword123"})
    assert c.get("/api/bootstrap").json["user"]["profile"]["skills"] == ["Algorithms"]


@pytest.mark.parametrize(
    "change_data",
    [
        {"modules": ["Fake module"]},
        {"preferences": ["Fake method"]},
        {"needs": [{"topic": "Python", "priority": 8}]},
        {"availability": [{"day": "Monday", "start": "18:00", "end": "16:00"}]},
        {"availability": [{"day": "Unknown", "start": "16:00", "end": "17:00"}]},
        {"skills": "Python"},
    ],
)
def test_profile_validation(app, change_data):
    c = app.test_client()
    register(c)
    assert send(c, "profile", "PUT", user_profile(**change_data)).status_code == 400


def test_matching_rank_score_reasons_and_stored_results(app):
    a, b = pair(app)
    send(a, "profile", "PUT", user_profile())
    send(
        b,
        "profile",
        "PUT",
        user_profile(name="Bob", skills=["Python"], needs=[{"topic": "Algorithms", "priority": 3}]),
    )
    p = a.get("/api/peers").json["peers"][0]
    assert p["score"] == 100 and len(p["reasons"]) == 6
    with sqlite3.connect(app.config["DATABASE"]) as c:
        assert c.execute("SELECT score FROM matches WHERE user_id=1").fetchone()[0] == 100


def test_priority_weighting_and_non_overlapping_availability(app):
    a, b = pair(app)
    send(
        a,
        "profile",
        "PUT",
        user_profile(
            needs=[{"topic": "Python", "priority": 3}, {"topic": "Calculus", "priority": 1}],
            preferences=[],
            interests=[],
            availability=[],
        ),
    )
    send(
        b,
        "profile",
        "PUT",
        user_profile(
            skills=["Python"], needs=[], modules=[], preferences=[], interests=[], availability=[]
        ),
    )
    assert a.get("/api/peers").json["peers"][0]["score"] == 30


def test_connection_restrictions_and_notifications(app):
    a, b = pair(app)
    assert send(a, "connections", data={"peer_id": 1}).status_code == 400
    assert send(a, "connections", data={"peer_id": 99}).status_code == 400
    assert send(a, "connections", data={"peer_id": 2}).status_code == 201
    assert send(b, "connections", data={"peer_id": 1}).status_code == 409
    assert send(a, "connections/1", "PATCH", {"status": "accepted"}).status_code == 403
    assert send(b, "connections/1", "PATCH", {"status": "declined"}).status_code == 200
    assert a.get("/api/activity").json["notifications"][-1]["message"]
    assert send(a, "connections", data={"peer_id": 2}).status_code == 201
    assert send(b, "connections/1", "PATCH", {"status": "accepted"}).status_code == 200


def test_session_workflow_accept_cancel_and_overlap(app):
    a, b, d = invitation(app)
    assert send(a, "sessions/1", "PATCH", {"status": "accepted"}).status_code == 400
    assert send(b, "sessions/1", "PATCH", {"status": "accepted"}).status_code == 200
    assert send(a, "sessions", data=d).status_code == 409
    assert send(a, "sessions/1", "PATCH", {"status": "completed"}).status_code == 400
    assert send(b, "sessions/1", "PATCH", {"status": "cancelled"}).status_code == 200
    assert send(a, "sessions/1", "PATCH", {"status": "completed"}).status_code == 400


def test_session_requires_connection_and_valid_future_time(app):
    a, b = pair(app)
    d = {
        "peer_id": 2,
        "module": "Computer Science",
        "topic": "Python",
        "starts": "2020-01-01T16:00",
        "duration": 60,
        "location": "Library",
    }
    assert send(a, "sessions", data=d).status_code == 403
    send(a, "connections", data={"peer_id": 2})
    send(b, "connections/1", "PATCH", {"status": "accepted"})
    assert send(a, "sessions", data=d).status_code == 400
    d["starts"] = "bad"
    assert send(a, "sessions", data=d).status_code == 400


def test_feedback_adapts_matches_and_cannot_repeat(app):
    a, b, _ = invitation(app)
    send(
        a,
        "profile",
        "PUT",
        user_profile(modules=[], skills=[], preferences=[], interests=[], availability=[]),
    )
    send(
        b,
        "profile",
        "PUT",
        user_profile(
            modules=[], skills=["Python"], needs=[], preferences=[], interests=[], availability=[]
        ),
    )
    initial = a.get("/api/peers").json["peers"][0]["score"]
    data = {"rating": 5, "useful": True, "again": True, "comments": "Helpful"}
    assert send(a, "sessions/1/feedback", data=data).status_code == 400
    send(b, "sessions/1", "PATCH", {"status": "accepted"})
    change(
        app,
        "UPDATE study_sessions SET starts=? WHERE id=1",
        ((datetime.now() - timedelta(days=1)).isoformat(timespec="minutes"),),
    )
    assert send(a, "sessions/1", "PATCH", {"status": "completed"}).status_code == 200
    assert send(a, "sessions/1/feedback", data={**data, "rating": 6}).status_code == 400
    assert send(a, "sessions/1/feedback", data=data).status_code == 201
    assert send(a, "sessions/1/feedback", data=data).status_code == 409
    updated = a.get("/api/peers").json["peers"][0]
    assert updated["score"] == initial + 10
    assert "feedback improves" in updated["reasons"][-1]
    assert (
        send(
            b,
            "sessions/1/feedback",
            data={"rating": 1, "useful": False, "again": False, "comments": ""},
        ).status_code
        == 201
    )
    assert a.get("/api/peers").json["peers"][0]["score"] == initial


def test_negative_feedback_lowers_match(app):
    a, b, _ = invitation(app)
    send(a, "profile", "PUT", user_profile())
    send(b, "profile", "PUT", user_profile(skills=["Python"]))
    initial = a.get("/api/peers").json["peers"][0]["score"]
    change(app, "UPDATE study_sessions SET status='completed' WHERE id=1")
    send(
        a,
        "sessions/1/feedback",
        data={"rating": 1, "useful": False, "again": False, "comments": ""},
    )
    assert a.get("/api/peers").json["peers"][0]["score"] == initial - 10


def test_third_party_cannot_manage_session(app):
    invitation(app)
    c = app.test_client()
    register(c, "charlie@uj.ac.za", "Charlie")
    assert not c.get("/api/activity").json["sessions"]
    assert send(c, "sessions/1", "PATCH", {"status": "cancelled"}).status_code == 403
    assert (
        send(
            c, "sessions/1/feedback", data={"rating": 5, "useful": True, "again": True}
        ).status_code
        == 403
    )


def test_admin_and_student_routes_are_separate(app):
    a, b = pair(app)
    assert a.get("/api/admin/overview").status_code == 403
    assert a.get("/admin/overview").status_code == 403
    change(app, "UPDATE users SET role='admin' WHERE id=1")
    assert a.get("/api/admin/overview").status_code == 200
    assert a.get("/api/peers").status_code == 403
    assert a.get("/api/activity").status_code == 403
    assert a.get("/").status_code == 302
    assert send(a, "admin/students/2", data={"action": "suspend"}).status_code == 200
    assert b.get("/api/peers").status_code == 401
    assert send(a, "admin/students/2", data={"action": "reactivate"}).status_code == 200
    assert (
        send(
            b, "login", data={"email": "bob@uj.ac.za", "password": "StrongPassword123"}
        ).status_code
        == 200
    )
    assert send(b, "admin/students/1", data={"action": "verify"}).status_code == 403


def test_notifications_read_only_affects_owner(app):
    a, b = pair(app)
    send(a, "connections", data={"peer_id": 2})
    send(a, "notifications/read")
    assert all(n["seen"] for n in a.get("/api/activity").json["notifications"])
    assert any(not n["seen"] for n in b.get("/api/activity").json["notifications"])


def test_upcoming_reminder_once(app):
    a, b, _ = invitation(app)
    send(b, "sessions/1", "PATCH", {"status": "accepted"})
    change(
        app,
        "UPDATE study_sessions SET starts=? WHERE id=1",
        (
            (
                datetime.now(timezone(timedelta(hours=2))).replace(tzinfo=None) + timedelta(hours=2)
            ).isoformat(timespec="minutes"),
        ),
    )
    a.get("/api/activity")
    result = a.get("/api/activity").json
    assert (
        len([n for n in result["notifications"] if n["message"].startswith("Upcoming session")])
        == 1
    )


def test_login_rate_limit(app):
    c = app.test_client()
    for _ in range(10):
        assert send(c, "login", data={"email": "bad@uj.ac.za", "password": "x"}).status_code == 401
    assert send(c, "login", data={"email": "bad@uj.ac.za", "password": "x"}).status_code == 429


@pytest.mark.parametrize("endpoint", ["peers", "activity", "admin/overview"])
def test_unauthenticated_routes(app, endpoint):
    assert app.test_client().get("/api/" + endpoint).status_code == 401
