"""Authorize the configured sender interactively; never sends an email itself."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from errors import AppError
from microsoft_mail import connect_mailbox

if __name__ == "__main__":
    try:
        with create_app().app_context():
            connect_mailbox()
    except AppError as error:
        raise SystemExit(error.message) from None
    except Exception:
        raise SystemExit(
            "Microsoft authorization could not be completed. Check tenant/app settings and network access."
        ) from None
