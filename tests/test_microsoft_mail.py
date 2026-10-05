import json
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import Mock

import pytest

from app import create_app
from errors import AppError
from mailer import deliver


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "mail-test-secret",
            "DATABASE": str(tmp_path / "mail.sqlite"),
            "MAIL_PROVIDER": "smtp",
            "SMTP_HOST": "smtp.office365.com",
            "SMTP_PORT": 587,
            "SMTP_SECURITY": "starttls",
            "SMTP_AUTH": "microsoft_oauth",
            "SMTP_USERNAME": "sender@university.ac.za",
            "SMTP_FROM": "sender@university.ac.za",
            "MICROSOFT_TENANT_ID": "00000000-0000-0000-0000-000000000001",
            "MICROSOFT_CLIENT_ID": "00000000-0000-0000-0000-000000000002",
            "MICROSOFT_TOKEN_CACHE": str(tmp_path / "cache.bin"),
        }
    )


def email():
    result = EmailMessage()
    result["From"] = "sender@university.ac.za"
    result["To"] = "student@university.ac.za"
    result.set_content("Test body")
    return result


def test_smtp_uses_tls_xoauth2_not_password(app, monkeypatch):
    import microsoft_mail

    connection = Mock()
    context = Mock()
    context.__enter__ = Mock(return_value=connection)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("mailer.smtplib.SMTP", Mock(return_value=context))
    monkeypatch.setattr(microsoft_mail, "access_token", lambda: "fake-test-access-token")
    with app.app_context():
        deliver(email())
    connection.starttls.assert_called_once()
    connection.login.assert_not_called()
    mechanism, callback = connection.auth.call_args.args
    assert mechanism == "XOAUTH2"
    assert (
        callback() == "user=sender@university.ac.za\x01auth=Bearer fake-test-access-token\x01\x01"
    )
    assert callback(b"challenge") == ""
    connection.send_message.assert_called_once()


def test_microsoft_rejects_unencrypted_and_mismatched_sender(app):
    with app.app_context():
        app.config["SMTP_SECURITY"] = "none"
        with pytest.raises(AppError, match="TLS"):
            deliver(email())
        app.config["SMTP_SECURITY"] = "starttls"
        app.config["SMTP_FROM"] = "other@university.ac.za"
        with pytest.raises(AppError, match="same Microsoft"):
            deliver(email())


def test_missing_app_registration_is_user_safe(app):
    from microsoft_mail import settings

    with app.app_context():
        app.config["MICROSOFT_CLIENT_ID"] = ""
        with pytest.raises(AppError, match="tenant ID and client ID"):
            settings()


def test_token_cache_encrypted_and_tampering_rejected(app, monkeypatch):
    import msal

    from microsoft_mail import load_client, save_cache, settings

    monkeypatch.setattr(msal, "PublicClientApplication", Mock())
    with app.app_context():
        _, _, _, path, cipher = settings()
        cache = msal.SerializableTokenCache()
        cache.deserialize(json.dumps({"testMarker": "secret-cache-content"}))
        cache.has_state_changed = True
        save_cache(cache, path, cipher)
        assert b"secret-cache-content" not in path.read_bytes()
        _, loaded, _, _, _ = load_client()
        assert "secret-cache-content" in loaded.serialize()
        path.write_bytes(b"tampered")
        with pytest.raises(AppError, match="connected again"):
            load_client()


def test_silent_refresh_and_missing_authorization(app, monkeypatch):
    import microsoft_mail

    fake = Mock()
    fake.get_accounts.return_value = [{"username": "sender@university.ac.za"}]
    fake.acquire_token_silent.return_value = {"access_token": "test-token"}
    monkeypatch.setattr(microsoft_mail.msal, "PublicClientApplication", Mock(return_value=fake))
    with app.app_context():
        assert microsoft_mail.access_token() == "test-token"
        fake.acquire_token_silent.assert_called_once()
        fake.get_accounts.return_value = []
        with pytest.raises(AppError, match="Connect the Microsoft"):
            microsoft_mail.access_token()


def test_connect_rejects_wrong_mailbox_without_saving_cache(app, monkeypatch, capsys):
    import microsoft_mail

    fake = Mock()
    fake.initiate_device_flow.return_value = {
        "user_code": "test-device-code",
        "message": "Test sign-in instruction",
    }
    fake.acquire_token_by_device_flow.return_value = {"access_token": "fake-test-token"}
    fake.get_accounts.return_value = []
    monkeypatch.setattr(microsoft_mail.msal, "PublicClientApplication", Mock(return_value=fake))
    with app.app_context():
        with pytest.raises(AppError, match="SMTP_USERNAME"):
            microsoft_mail.connect_mailbox()
        assert not Path(app.config["MICROSOFT_TOKEN_CACHE"]).exists()
    assert "fake-test-token" not in capsys.readouterr().out
