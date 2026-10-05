"""python scripts/manage.py cleanup-demo|setup-admin|dispatch-announcements"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

from maintenance import cleanup_demo, setup_admin


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["cleanup-demo", "setup-admin", "seed-test-admin", "dispatch-announcements"],
    )
    command = parser.parse_args().command
    if command == "seed-test-admin":
        from app import create_app
        from seed_service import seed_test_admins

        with create_app().app_context():
            print(
                f"Seeded {seed_test_admins()} test administrator(s). TEST ONLY — do not use in production."
            )
        return
    if command == "dispatch-announcements":
        from admin_service import dispatch_announcements
        from app import create_app

        with create_app().app_context():
            print(f"Dispatched {dispatch_announcements()} announcements.")
        return
    path = Path(os.environ.get("DATABASE_PATH", "instance/adaptolearn.sqlite3")).resolve()
    if not path.exists():
        raise SystemExit("Database does not exist. Start run.py once first.")
    backup = path.with_name(
        path.stem + ".backup-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + ".sqlite3"
    )
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    with sqlite3.connect(backup) as destination:
        c.backup(destination)
    from migrations import upgrade

    upgrade(c)
    if command == "cleanup-demo":
        print(f"Removed {cleanup_demo(c)} known demo accounts. Backup: {backup}")
    else:
        secret = os.environ.get("ADMIN_INITIAL_PASSWORD", "")
        uid = setup_admin(c, secret, os.environ.get("ADMIN_OLD_EMAIL"))
        print(
            f"Administrator {uid} configured; first-login password reset required. Backup: {backup}"
        )
    c.close()


if __name__ == "__main__":
    main()
