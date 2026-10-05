"""Explicit development seed; never run automatically by production startup."""

from datetime import datetime, timezone

import bcrypt

from database import transaction
from errors import AppError
from institutions import DUT_ID
from password_hashing import password_matches
from test_users import TEST_USERS


def seed_test_admins() -> int:
    count = 0
    with transaction() as c:
        for config in TEST_USERS:
            existing = c.execute("SELECT * FROM users WHERE email=?", (config["email"],)).fetchone()
            if existing and existing["role"] != "admin":
                raise AppError("The test admin address belongs to a student; seeding refused.", 409)
            hashed = (
                existing["password"]
                if existing
                and existing["password"].startswith("$2")
                and password_matches(existing["password"], config["password"])
                else bcrypt.hashpw(config["password"].encode(), bcrypt.gensalt()).decode()
            )
            if existing:
                changed = (
                    existing["password"] != hashed
                    or not existing["email_verified"]
                    or existing["status"] != "ACTIVE"
                    or not existing["active"]
                    or existing["must_reset_password"]
                    or existing["admin_level"] != "super-admin"
                )
                if changed:
                    c.execute(
                        "UPDATE users SET password=?,role='admin',email_verified=1,status='ACTIVE',active=1,admin_level='super-admin',must_reset_password=0,auth_version=auth_version+1 WHERE id=?",
                        (hashed, existing["id"]),
                    )
            else:
                c.execute(
                    "INSERT INTO users(name,email,password,institution_id,programme,year,role,email_verified,status,admin_level,must_reset_password,created) VALUES(?,?,?,?,?,1,'admin',1,'ACTIVE','super-admin',0,?)",
                    (
                        config["firstName"] + " " + config["lastName"],
                        config["email"],
                        hashed,
                        DUT_ID,
                        "Administration",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            count += 1
    return count
