"""Microsoft 365 delegated SMTP OAuth, with encrypted server-only token caching."""

import base64
import hashlib
import os
import threading
from pathlib import Path
from uuid import UUID

import msal
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from errors import AppError

SCOPES = ["https://outlook.office.com/SMTP.Send"]
_lock = threading.RLock()


def settings() -> tuple[str, str, str, Path, Fernet]:
    c = current_app.config
    tenant = c.get("MICROSOFT_TENANT_ID", "").strip()
    client = c.get("MICROSOFT_CLIENT_ID", "").strip()
    sender = c.get("SMTP_USERNAME", "").strip().lower()
    try:
        UUID(tenant)
        UUID(client)
    except (ValueError, TypeError):
        raise AppError(
            "Microsoft email setup needs a valid tenant ID and client ID in .env.", 503
        ) from None
    if not sender or "@" not in sender:
        raise AppError("Set SMTP_USERNAME to the Microsoft 365 sending mailbox.", 503)
    path = Path(c["MICROSOFT_TOKEN_CACHE"]).resolve()
    key = base64.urlsafe_b64encode(hashlib.sha256(c["SECRET_KEY"].encode()).digest())
    return tenant, client, sender, path, Fernet(key)


def load_client():
    tenant, client, sender, path, cipher = settings()
    cache = msal.SerializableTokenCache()
    if path.exists():
        try:
            cache.deserialize(cipher.decrypt(path.read_bytes()).decode())
        except (InvalidToken, ValueError, UnicodeError, OSError):
            raise AppError(
                "Microsoft email authorization needs to be connected again.", 503
            ) from None
    app = msal.PublicClientApplication(
        client, authority="https://login.microsoftonline.com/" + tenant, token_cache=cache
    )
    return app, cache, sender, path, cipher


def save_cache(cache, path: Path, cipher: Fernet) -> None:
    if not cache.has_state_changed:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(cipher.encrypt(cache.serialize().encode()))
    os.replace(temporary, path)


def access_token() -> str:
    with _lock:
        try:
            app, cache, sender, path, cipher = load_client()
            accounts = app.get_accounts(username=sender)
            if not accounts:
                raise AppError(
                    "Connect the Microsoft sending mailbox with scripts/connect_microsoft_mail.py.",
                    503,
                )
            result = app.acquire_token_silent(SCOPES, account=accounts[0])
            save_cache(cache, path, cipher)
        except AppError:
            raise
        except Exception:
            raise AppError(
                "Microsoft email authorization is unavailable. Reconnect the sending mailbox.", 503
            ) from None
    if not result or not result.get("access_token"):
        raise AppError("Microsoft email authorization expired. Reconnect the sending mailbox.", 503)
    return result["access_token"]


def connect_mailbox() -> None:
    with _lock:
        app, cache, sender, path, cipher = load_client()
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise AppError(
                "Microsoft could not start sign-in. Check the app permissions and public-client setting.",
                503,
            )
        # This interactive CLI displays Microsoft's one-time sign-in instructions only.
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)
        if not result.get("access_token"):
            raise AppError(
                "Microsoft sign-in failed or was declined. Check tenant consent and account policies.",
                503,
            )
        if not app.get_accounts(username=sender):
            raise AppError("Sign in using the mailbox configured in SMTP_USERNAME.", 400)
        save_cache(cache, path, cipher)
        print("Microsoft sending mailbox connected. Restart run.py.")
