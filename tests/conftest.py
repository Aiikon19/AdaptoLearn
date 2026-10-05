import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    mailbox = []
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "security-tests",
            "DATABASE": str(tmp_path / "security.sqlite"),
            "TEST_MAILER": mailbox.append,
        }
    )
    application.extensions["mailbox"] = mailbox
    return application
