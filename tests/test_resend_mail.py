import time
from unittest.mock import Mock

import pytest
import requests

from app import create_app
from database import db
from mailer import send_verification
from tests_helpers import registration, send


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "resend-test",
            "DATABASE": str(tmp_path / "test.sqlite"),
            "MAIL_PROVIDER": "resend",
            "RESEND_API_KEY": "fake-test-key",
            "ANNOUNCEMENT_WORKER": False,
        }
    )


def test_registration_http_payload_and_single_use(app, monkeypatch):
    post = Mock(return_value=Mock(status_code=200))
    monkeypatch.setattr("mailer.requests.post", post)
    monkeypatch.setattr("verification.generate_code", lambda: "000007")
    client = app.test_client()
    assert send(client, "register", data=registration()).status_code == 201
    args, kwargs = post.call_args
    assert args == ("https://api.resend.com/emails",)
    assert kwargs["headers"]["Authorization"] == "Bearer fake-test-key"
    payload = kwargs["json"]
    assert payload["from"] == "Registration System <onboarding@resend.dev>"
    assert payload["to"] == ["221234567@dut4life.ac.za"]
    assert payload["subject"] == "000007 is your registration verification code"
    assert "000007" in payload["html"] and "15 minutes" in payload["html"]
    with app.app_context():
        record = db().execute("SELECT * FROM verification_codes").fetchone()
        assert 895 < record["expires_at"] - time.time() <= 900
        assert "000007" not in record["code_hash"]
    assert (
        send(
            client, "verify", data={"email": "someone@dut4life.ac.za", "code": "000007"}
        ).status_code
        == 400
    )
    assert (
        send(
            client, "verify", data={"email": "221234567@dut4life.ac.za", "code": "000007"}
        ).status_code
        == 200
    )
    with app.app_context():
        assert db().execute("SELECT email_verified FROM users").fetchone()[0] == 1
    assert send(client, "verify", data={"code": "000007"}).status_code == 400


@pytest.mark.parametrize("error", [requests.Timeout(), requests.HTTPError()])
def test_delivery_failure_rolls_back_account(app, monkeypatch, error):
    response = Mock()
    response.raise_for_status.side_effect = error
    monkeypatch.setattr("mailer.requests.post", Mock(return_value=response))
    result = send(app.test_client(), "register", data=registration())
    assert result.status_code == 503 and "fake-test-key" not in result.get_data(as_text=True)
    with app.app_context():
        assert db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert db().execute("SELECT COUNT(*) FROM verification_codes").fetchone()[0] == 0


def test_expiration_at_exact_fifteen_minutes(app, monkeypatch):
    monkeypatch.setattr("mailer.requests.post", Mock(return_value=Mock()))
    monkeypatch.setattr("verification.generate_code", lambda: "000007")
    client = app.test_client()
    assert send(client, "register", data=registration()).status_code == 201
    with app.app_context():
        expiry = db().execute("SELECT expires_at FROM verification_codes").fetchone()[0]
    monkeypatch.setattr("verification.time.time", lambda: expiry)
    assert send(client, "verify", data={"code": "000007"}).status_code == 400
    with app.app_context():
        assert db().execute("SELECT email_verified FROM users").fetchone()[0] == 0


def test_missing_key_and_html_escaping(app, monkeypatch):
    post = Mock()
    monkeypatch.setattr("mailer.requests.post", post)
    app.config["RESEND_API_KEY"] = ""
    assert send(app.test_client(), "register", data=registration()).status_code == 503
    post.assert_not_called()
    app.config["RESEND_API_KEY"] = "fake-test-key"
    with app.app_context():
        send_verification("221234567@dut4life.ac.za", "<script>bad</script>", "000007")
    assert "<script>" not in post.call_args.kwargs["json"]["html"]
