import smtplib
import ssl
from email.message import EmailMessage
from html import escape

import requests
from flask import current_app

from errors import AppError


def send_verification(email: str, institution_name: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = f"{code} is your registration verification code"
    message["To"] = email
    message["From"] = (
        "Registration System <onboarding@resend.dev>"
        if current_app.config.get("MAIL_PROVIDER", "resend") == "resend"
        else current_app.config.get("SMTP_FROM", "")
    )
    message.set_content(
        f"Welcome to AdaptoLearn.\n\nInstitution: {institution_name}\n\nYour verification code is: {code}\n\nThis code expires in 15 minutes. Do not share this code.\nIf you did not request this email, you can ignore it."
    )
    message.add_alternative(
        f"""<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:24px 12px;background:#f3f6fa;font-family:Arial,sans-serif;color:#172b40">
<div style="max-width:520px;margin:auto;background:white;border-radius:16px;padding:32px 24px">
<p style="color:#16736b;font-weight:bold">AdaptoLearn</p><h1 style="font-size:24px">Verify your student email</h1>
<p>Welcome! Confirm your registration at {escape(institution_name)} with this code:</p>
<div style="text-align:center;background:#edf7f5;border:1px solid #bee1dc;border-radius:12px;padding:24px 8px;font-size:36px;letter-spacing:6px;font-weight:bold">{escape(code)}</div>
<p>This code expires in <strong>15 minutes</strong>. Do not share this code.</p>
<p style="font-size:13px;color:#617183">If you did not request this email, you can ignore it.</p>
</div></body></html>""",
        subtype="html",
    )
    deliver(message)


def send_password_reset(email: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Your AdaptoLearn password reset code"
    message["To"] = email
    message["From"] = (
        "Registration System <onboarding@resend.dev>"
        if current_app.config.get("MAIL_PROVIDER", "resend") == "resend"
        else current_app.config.get("SMTP_FROM", "")
    )
    message.set_content(
        f"Your AdaptoLearn password reset code is: {code}\n\nThis code expires in 10 minutes. Do not share this code.\nIf you did not request a password reset, ignore this email. Your password has not changed."
    )
    deliver(message)


def deliver(message: EmailMessage) -> None:
    test_mailer = current_app.config.get("TEST_MAILER")
    if current_app.testing and test_mailer:
        test_mailer(message)
        return
    c = current_app.config
    if c.get("MAIL_PROVIDER", "resend") == "resend":
        key = c.get("RESEND_API_KEY", "").strip()
        if not key:
            raise AppError(
                "Email delivery is not configured. Set RESEND_API_KEY on the server.", 503
            )
        plain = message.get_body(preferencelist=("plain",))
        html = message.get_body(preferencelist=("html",))
        payload = {
            "from": "Registration System <onboarding@resend.dev>",
            "to": [str(message["To"])],
            "subject": str(message["Subject"]),
            "text": plain.get_content() if plain else "",
        }
        if html:
            payload["html"] = html.get_content()
        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
                timeout=(5, 15),
            )
            response.raise_for_status()
        except requests.RequestException:
            raise AppError(
                "The email could not be delivered. Check the Resend sender, recipient permissions, and quota, then try again.",
                503,
            ) from None
        return
    if not c.get("SMTP_HOST") or not c.get("SMTP_FROM"):
        raise AppError("Email delivery is not configured. Please contact the administrator.", 503)
    token = None
    if c["SMTP_AUTH"] == "microsoft_oauth":
        if c["SMTP_SECURITY"] == "none":
            raise AppError("Microsoft email requires TLS encryption.", 503)
        if c["SMTP_FROM"].strip().lower() != c.get("SMTP_USERNAME", "").strip().lower():
            raise AppError(
                "Set SMTP_FROM and SMTP_USERNAME to the same Microsoft sending mailbox.", 503
            )
        from microsoft_mail import access_token

        token = access_token()
    try:
        transport = smtplib.SMTP_SSL if c["SMTP_SECURITY"] == "ssl" else smtplib.SMTP
        with transport(c["SMTP_HOST"], c["SMTP_PORT"], timeout=15) as client:
            if c["SMTP_SECURITY"] == "starttls":
                client.starttls(context=ssl.create_default_context())
            if token:
                payload = f"user={c['SMTP_USERNAME']}\x01auth=Bearer {token}\x01\x01"
                client.auth("XOAUTH2", lambda challenge=None: payload if challenge is None else "")
            elif c.get("SMTP_USERNAME"):
                client.login(c["SMTP_USERNAME"], c["SMTP_PASSWORD"])
            client.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise AppError("The email could not be delivered. Please try again later.", 503) from None
