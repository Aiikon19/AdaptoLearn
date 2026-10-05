import json
import time
from datetime import datetime, timezone

from database import db, rows, transaction
from errors import AppError
from maintenance import delete_user_records
from validation import validate_student_email
from verification import endpoint_limits, issue_code


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit(actor: dict, action: str, target: str, details: dict | None = None) -> None:
    db().execute(
        "INSERT INTO audit_log(actor_id,actor_name,action,target,created,details) VALUES(?,?,?,?,?,?)",
        (actor["id"], actor["name"], action, target, stamp(), json.dumps(details or {})),
    )


def overview() -> dict:
    return {
        "totalStudents": db()
        .execute("SELECT COUNT(*) FROM users WHERE role='student'")
        .fetchone()[0],
        "pendingVerifications": db()
        .execute(
            "SELECT COUNT(*) FROM users WHERE role='student' AND status='PENDING_VERIFICATION'"
        )
        .fetchone()[0],
        "verifiedStudents": db()
        .execute("SELECT COUNT(*) FROM users WHERE role='student' AND email_verified=1")
        .fetchone()[0],
        "activeInstitutions": db()
        .execute("SELECT COUNT(*) FROM institutions WHERE is_active=1")
        .fetchone()[0],
        "recentSignups": rows(
            "SELECT u.id,u.name,u.email,u.institution_id,u.status,u.email_verified,u.active,u.created,i.name institution FROM users u JOIN institutions i ON i.id=u.institution_id WHERE role='student' ORDER BY u.id DESC LIMIT 10"
        ),
    }


def students(query: str = "", institution: int | None = None, status: str = "") -> list[dict]:
    if len(query) > 100 or status not in ["", "ACTIVE", "PENDING_VERIFICATION", "SUSPENDED"]:
        raise AppError("Invalid search filter.")
    if institution is not None and not 1 <= institution <= 26:
        raise AppError("Invalid institution filter.")
    return rows(
        "SELECT u.id,u.name,u.email,u.institution_id,u.status,u.email_verified,u.active,u.created,i.name institution FROM users u JOIN institutions i ON i.id=u.institution_id WHERE role='student' AND (u.name LIKE ? OR u.email LIKE ?) AND (? IS NULL OR institution_id=?) AND (?='' OR status=?) ORDER BY u.id DESC",
        ("%" + query + "%", "%" + query + "%", institution, institution, status, status),
    )


def student_detail(uid: int) -> dict:
    result = rows(
        "SELECT u.id,u.name,u.email,u.institution_id,u.status,u.email_verified,u.active,u.created,i.name institution,u.programme,u.year FROM users u JOIN institutions i ON i.id=u.institution_id WHERE u.id=? AND role='student'",
        (uid,),
    )
    if not result:
        raise AppError("Student not found.", 404)
    return result[0]


def student_action(actor: dict, uid: int, action: str, ip: str) -> None:
    with transaction() as c:
        user = student_detail(uid)
        if action == "delete":
            delete_user_records(c, uid)
        elif action == "resend":
            endpoint_limits("resend", ip, uid)
            issue_code(uid, True)
        elif action == "verify":
            institution = c.execute(
                "SELECT * FROM institutions WHERE id=?", (user["institution_id"],)
            ).fetchone()
            validate_student_email(user["email"], institution)
            if user["status"] == "SUSPENDED":
                raise AppError("Reactivate the student before verification.")
            c.execute(
                "UPDATE users SET email_verified=1,status='ACTIVE',auth_version=auth_version+1 WHERE id=?",
                (uid,),
            )
            c.execute(
                "UPDATE verification_codes SET consumed_at=? WHERE user_id=? AND consumed_at IS NULL",
                (time.time(), uid),
            )
        elif action == "unverify":
            c.execute(
                "UPDATE users SET email_verified=0,status=CASE WHEN active=1 THEN 'PENDING_VERIFICATION' ELSE 'SUSPENDED' END,auth_version=auth_version+1 WHERE id=?",
                (uid,),
            )
            c.execute(
                "UPDATE verification_codes SET consumed_at=? WHERE user_id=? AND consumed_at IS NULL",
                (time.time(), uid),
            )
        elif action == "suspend":
            c.execute(
                "UPDATE users SET active=0,status='SUSPENDED',auth_version=auth_version+1 WHERE id=?",
                (uid,),
            )
        elif action == "reactivate":
            c.execute(
                "UPDATE users SET active=1,status=CASE WHEN email_verified=1 THEN 'ACTIVE' ELSE 'PENDING_VERIFICATION' END,auth_version=auth_version+1 WHERE id=?",
                (uid,),
            )
        audit(actor, "student." + action, str(uid))


def update_institution(actor: dict, iid: int, data: dict) -> None:
    with transaction() as c:
        before = c.execute("SELECT * FROM institutions WHERE id=?", (iid,)).fetchone()
        if not before:
            raise AppError("Institution not found.", 404)
        c.execute(
            "UPDATE institutions SET student_email_domain=?,is_active=? WHERE id=?",
            (data["studentEmailDomain"], int(data["isActive"]), iid),
        )
        if before["student_email_domain"] != data["studentEmailDomain"]:
            c.execute(
                "UPDATE verification_codes SET consumed_at=? WHERE consumed_at IS NULL AND user_id IN (SELECT id FROM users WHERE institution_id=?)",
                (time.time(), iid),
            )
        audit(actor, "institution.update", str(iid), data)


def require_super(actor: dict) -> None:
    if actor["admin_level"] != "super-admin":
        raise AppError("Super-admin access required.", 403)


def admins(actor: dict) -> list[dict]:
    require_super(actor)
    return rows(
        "SELECT id,name,email,admin_level,active,must_reset_password FROM users WHERE role='admin' ORDER BY id"
    )


def update_admin(actor: dict, uid: int, data: dict) -> None:
    require_super(actor)
    with transaction() as c:
        target = c.execute("SELECT * FROM users WHERE id=? AND role='admin'", (uid,)).fetchone()
        if not target:
            raise AppError("Administrator not found.", 404)
        if uid == actor["id"] and (not data["active"] or data["adminLevel"] != "super-admin"):
            raise AppError("You cannot deactivate or demote your own account.")
        c.execute(
            "UPDATE users SET active=?,status=?,admin_level=?,auth_version=auth_version+1 WHERE id=?",
            (
                int(data["active"]),
                "ACTIVE" if data["active"] else "SUSPENDED",
                data["adminLevel"],
                uid,
            ),
        )
        audit(actor, "admin.update", str(uid), data)


def create_announcement(actor: dict, data: dict) -> None:
    when = time.time()
    if data["send_at"]:
        try:
            parsed = datetime.fromisoformat(data["send_at"])
            if parsed.tzinfo is None:
                raise ValueError()
            when = parsed.timestamp()
        except ValueError:
            raise AppError("Use a date/time with a time zone.", field="send_at") from None
        if when < time.time():
            raise AppError("Choose a future scheduled time.", field="send_at")
    if not data["title"].strip() or not data["body"].strip():
        raise AppError("Title and notice are required.")
    if (
        data["institution_id"] is not None
        and not db()
        .execute("SELECT id FROM institutions WHERE id=?", (data["institution_id"],))
        .fetchone()
    ):
        raise AppError("Institution not found.")
    with transaction() as c:
        uid = c.execute(
            "INSERT INTO announcements(actor_id,title,body,institution_id,send_at,created) VALUES(?,?,?,?,?,?)",
            (
                actor["id"],
                data["title"].strip(),
                data["body"].strip(),
                data["institution_id"],
                when,
                stamp(),
            ),
        ).lastrowid
        audit(actor, "announcement.create", str(uid))
    dispatch_announcements()


def dispatch_announcements() -> int:
    with transaction() as c:
        pending = c.execute(
            "SELECT * FROM announcements WHERE sent_at IS NULL AND send_at<=?", (time.time(),)
        ).fetchall()
        for notice in pending:
            recipients = c.execute(
                "SELECT id FROM users WHERE role='student' AND active=1 AND email_verified=1 AND (? IS NULL OR institution_id=?)",
                (notice["institution_id"], notice["institution_id"]),
            ).fetchall()
            c.executemany(
                "INSERT INTO notifications(user_id,message,created) VALUES(?,?,?)",
                [(u["id"], notice["title"] + "\n" + notice["body"], stamp()) for u in recipients],
            )
            c.execute("UPDATE announcements SET sent_at=? WHERE id=?", (time.time(), notice["id"]))
        return len(pending)
