import json
import mimetypes
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, g, jsonify, render_template, request, session

from access import current_user, establish_session
from access import student_required as login_required
from admin_routes import admin as admin_blueprint
from auth_service import authenticate, register_student, reset_admin_password
from database import db, execute, rows
from errors import AppError
from institutions import DUT_ID
from migrations import upgrade
from password_recovery import REQUEST_MESSAGE, complete_reset, request_reset
from validation import SCHEMAS, institution_records, validate, validate_student_email
from verification import endpoint_limits, issue_code, verify_code

BASE = Path(__file__).resolve().parent
# Windows registry associations can incorrectly identify JavaScript as plain text.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
METHODS = [
    "One-on-one",
    "Group learning",
    "Practical exercises",
    "Discussions",
    "Online",
    "In person",
]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def now():
    return datetime.now(timezone.utc).isoformat()


def notify(uid, message):
    execute(
        "INSERT INTO notifications(user_id,message,created) VALUES(?,?,?)", (uid, message, now())
    )


def public_user(user):
    u = dict(user)
    u.pop("password", None)
    u.pop("email", None)
    u.pop("auth_version", None)
    u["profile"] = json.loads(u["profile"])
    return u


def clean_text(value, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        abort(400, description=f"Enter valid text (1–{maximum} characters).")
    return value.strip()


def integer(value, low, high):
    try:
        result = int(value)
    except (ValueError, TypeError):
        abort(400, description="Enter a valid number.")
    if not low <= result <= high:
        abort(400, description=f"Number must be between {low} and {high}.")
    return result


def profile_data(data):
    result = {}
    for key in ["modules", "skills", "interests", "preferences"]:
        values = data.get(key, [])
        if not isinstance(values, list) or len(values) > 30:
            abort(400, description="Profile fields must contain up to 30 entries.")
        result[key] = list(dict.fromkeys(clean_text(v, 80) for v in values))
    available = {r["name"] for r in rows("SELECT name FROM modules WHERE active=1")}
    if not set(result["modules"]).issubset(available) or not set(result["preferences"]).issubset(
        METHODS
    ):
        abort(400, description="Choose a listed module or learning preference.")
    needs = data.get("needs", [])
    if (
        not isinstance(needs, list)
        or len(needs) > 30
        or any(not isinstance(n, dict) for n in needs)
    ):
        abort(400, description="Enter up to 30 learning needs.")
    result["needs"] = [
        {"topic": clean_text(n.get("topic"), 80), "priority": integer(n.get("priority"), 1, 3)}
        for n in needs
        if isinstance(n, dict)
    ]
    slots = data.get("availability", [])
    if not isinstance(slots, list) or len(slots) > 21:
        abort(400, description="Enter up to 21 availability slots.")
    result["availability"] = []
    for s in slots:
        if not isinstance(s, dict) or s.get("day") not in DAYS:
            abort(400, description="Choose a valid day.")
        start, end = s.get("start", ""), s.get("end", "")
        if (
            not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start)
            or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end)
            or start >= end
        ):
            abort(400, description="Availability end time must follow its start time.")
        result["availability"].append({"day": s["day"], "start": start, "end": end})
    result["bio"] = str(data.get("bio", "")).strip()[:500]
    return result


def match_users(me, peer):
    a, b = json.loads(me["profile"]), json.loads(peer["profile"])
    reasons, score = [], 0.0

    def norm(values):
        return {v.casefold() for v in values}

    total = sum(n["priority"] for n in a.get("needs", []))
    covered = [n for n in a.get("needs", []) if n["topic"].casefold() in norm(b.get("skills", []))]
    if covered:
        score += 40 * sum(n["priority"] for n in covered) / max(total, 1)
        reasons.append("Can help with " + ", ".join(n["topic"] for n in covered))
    reciprocal = [
        n["topic"] for n in b.get("needs", []) if n["topic"].casefold() in norm(a.get("skills", []))
    ]
    if reciprocal:
        score += 10
        reasons.append("You can help with " + ", ".join(reciprocal))
    common = norm(a.get("modules", [])) & norm(b.get("modules", []))
    if common:
        score += 20 * len(common) / max(len(a.get("modules", [])), 1)
        reasons.append(
            "Shared module: " + ", ".join(v for v in a["modules"] if v.casefold() in common)
        )
    overlap = any(
        x["day"] == y["day"] and max(x["start"], y["start"]) < min(x["end"], y["end"])
        for x in a.get("availability", [])
        for y in b.get("availability", [])
    )
    if overlap:
        score += 15
        reasons.append("Your available study times overlap")
    if norm(a.get("preferences", [])) & norm(b.get("preferences", [])):
        score += 10
        reasons.append("Compatible learning preferences")
    if norm(a.get("interests", [])) & norm(b.get("interests", [])):
        score += 5
        reasons.append("Interests in common")
    history = rows(
        "SELECT f.* FROM feedback f JOIN study_sessions s ON s.id=f.session_id WHERE (s.creator=? AND s.peer=?) OR (s.creator=? AND s.peer=?)",
        (me["id"], peer["id"], peer["id"], me["id"]),
    )
    if history:
        adjustment = sum(
            (f["rating"] - 3) * 3 + (2 if f["useful"] else -2) + (2 if f["again"] else -2)
            for f in history
        ) / len(history)
        score += adjustment
        reasons.append(
            "Previous session feedback improves this match"
            if adjustment > 0
            else "Previous session feedback lowers this match"
            if adjustment < 0
            else "Previous session feedback is neutral"
        )
    return max(0, min(100, round(score))), reasons or [
        "Complete your learning profile to discover shared strengths"
    ]


def recommendations(uid):
    me = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    result = []
    for peer in (
        db()
        .execute(
            "SELECT u.*,i.name institution,i.acronym FROM users u JOIN institutions i ON i.id=u.institution_id WHERE u.id<>? AND u.active=1 AND u.role='student' AND u.email_verified=1 AND u.status='ACTIVE'",
            (uid,),
        )
        .fetchall()
    ):
        score, reasons = match_users(me, peer)
        execute(
            "INSERT OR REPLACE INTO matches VALUES(?,?,?,?,?)",
            (uid, peer["id"], score, json.dumps(reasons), now()),
        )
        u = public_user(peer)
        u.update(score=score, reasons=reasons)
        result.append(u)
    return sorted(result, key=lambda u: (-u["score"], u["name"]))


def create_app(config=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.update(
        DATABASE=os.environ.get("DATABASE_PATH", str(BASE / "instance" / "adaptolearn.sqlite3")),
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        MAX_CONTENT_LENGTH=65536,
        SMTP_HOST=os.environ.get("SMTP_HOST", ""),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USERNAME=os.environ.get("SMTP_USERNAME", ""),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
        SMTP_FROM=os.environ.get("SMTP_FROM", ""),
        SMTP_SECURITY=os.environ.get("SMTP_SECURITY", "starttls"),
    )
    app.config.update(
        SMTP_AUTH=os.environ.get("SMTP_AUTH", "password"),
        MICROSOFT_TENANT_ID=os.environ.get("MICROSOFT_TENANT_ID", ""),
        MICROSOFT_CLIENT_ID=os.environ.get("MICROSOFT_CLIENT_ID", ""),
        MICROSOFT_TOKEN_CACHE=os.environ.get(
            "MICROSOFT_TOKEN_CACHE",
            str(Path(app.config["DATABASE"]).parent / "microsoft-mail-cache.bin"),
        ),
    )
    if config:
        app.config.update(config)
    app.config.setdefault("MAIL_PROVIDER", os.environ.get("MAIL_PROVIDER", "resend"))
    app.config.setdefault("RESEND_API_KEY", os.environ.get("RESEND_API_KEY", ""))
    if app.config["MAIL_PROVIDER"] not in ["resend", "smtp"]:
        raise RuntimeError("MAIL_PROVIDER must be resend or smtp.")
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Set SECRET_KEY in the environment or .env before starting.")
    if app.config["MAIL_PROVIDER"] == "smtp" and app.config["SMTP_SECURITY"] not in [
        "ssl",
        "starttls",
        "none",
    ]:
        raise RuntimeError("SMTP_SECURITY must be ssl, starttls, or none.")
    if app.config["MAIL_PROVIDER"] == "smtp" and app.config["SMTP_AUTH"] not in [
        "password",
        "microsoft_oauth",
    ]:
        raise RuntimeError("SMTP_AUTH must be password or microsoft_oauth.")
    app.register_blueprint(admin_blueprint)

    @app.errorhandler(AppError)
    def app_error(e):
        return jsonify(error=e.message, field=e.field), e.status

    @app.before_request
    def before():
        if request.path.startswith("/api/") and request.method != "GET":
            if not secrets.compare_digest(
                session.get("csrf", ""), request.headers.get("X-CSRF-Token", "")
            ) or not session.get("csrf"):
                abort(400, description="Security token expired. Refresh this page.")
            if request.content_length and not isinstance(request.get_json(), dict):
                abort(400, description="Request data must be a JSON object.")
            if request.path.startswith(
                ("/api/connections", "/api/sessions", "/api/profile", "/api/notifications")
            ):
                db().execute("BEGIN IMMEDIATE")

    @app.teardown_appcontext
    def close(_):
        if "db" in g:
            g.db.close()

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(429)
    def error(e):
        return jsonify(error=e.description), e.code

    @app.after_request
    def headers(response):
        if "db" in g and g.db.in_transaction:
            if response.status_code < 400:
                g.db.commit()
            else:
                g.db.rollback()
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        user = current_user()
        if user and user["role"] == "admin":
            from flask import redirect

            return redirect("/admin/overview")
        return render_template("index.html")

    @app.get("/health")
    def health():
        db().execute("SELECT 1")
        return jsonify(status="ok")

    @app.get("/api/bootstrap")
    def bootstrap():
        session.setdefault("csrf", secrets.token_hex(24))
        authenticated = current_user()
        user = None
        if authenticated:
            user = (
                db()
                .execute(
                    "SELECT u.*,i.name institution,i.acronym FROM users u JOIN institutions i ON i.id=u.institution_id WHERE u.id=?",
                    (authenticated["id"],),
                )
                .fetchone()
            )
        pending = (
            db()
            .execute(
                "SELECT email FROM users WHERE id=? AND role='student' AND status='PENDING_VERIFICATION' AND active=1",
                (session.get("pending_uid"),),
            )
            .fetchone()
        )
        return jsonify(
            csrf=session["csrf"],
            user=public_user(user) if user else None,
            institutions=institution_records(db()),
            modules=rows("SELECT * FROM modules WHERE active=1 ORDER BY name"),
            methods=METHODS,
            days=DAYS,
            pendingEmail=pending["email"] if pending else None,
            resetRequired=bool(session.get("reset_uid")),
            defaultInstitutionId=DUT_ID,
            schemas=SCHEMAS,
        )

    @app.post("/api/register")
    def register():
        uid = register_student(
            validate("register", request.get_json()), request.remote_addr or "unknown"
        )
        session.clear()
        session["pending_uid"] = uid
        session["csrf"] = secrets.token_hex(24)
        return jsonify(ok=True, pendingVerification=True), 201

    @app.post("/api/login")
    def login():
        data = validate("login", request.get_json())
        user = authenticate(
            data["email"], data["password"], data["role"], request.remote_addr or "unknown"
        )
        session.clear()
        session["csrf"] = secrets.token_hex(24)
        if user["role"] == "student" and (not user["email_verified"] or user["status"] != "ACTIVE"):
            session["pending_uid"] = user["id"]
            return jsonify(ok=True, pendingVerification=True)
        if user["role"] == "admin" and user["must_reset_password"]:
            session["reset_uid"] = user["id"]
            session["reset_version"] = user["auth_version"]
            return jsonify(ok=True, resetRequired=True)
        establish_session(user)
        return jsonify(ok=True, redirect="/admin/overview" if user["role"] == "admin" else "/")

    @app.post("/api/verify")
    def verify():
        uid = session.get("pending_uid")
        endpoint_limits("verify", request.remote_addr or "unknown", uid)
        if not uid:
            raise AppError("Invalid or expired code", 400, "code")
        # Malformed attempts also consume the account's attempt budget.
        try:
            data = validate("verify", request.get_json())
        except AppError:
            data = {"code": ""}
        if "email" in data:
            pending = db().execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()
            if not pending or pending["email"] != data["email"].strip().lower():
                data["code"] = ""
        user = verify_code(uid, data["code"])
        establish_session(user)
        return jsonify(ok=True)

    @app.post("/api/verification/resend")
    def resend():
        uid = session.get("pending_uid")
        endpoint_limits("resend", request.remote_addr or "unknown", uid)
        if not uid:
            raise AppError("Unable to send a verification code.")
        issue_code(uid, True)
        return jsonify(ok=True)

    @app.post("/api/auth/forgot-password")
    def forgot_password():
        data = validate("forgotPassword", request.get_json())
        request_reset(data["email"], request.remote_addr or "unknown")
        return jsonify(ok=True, message=REQUEST_MESSAGE)

    @app.post("/api/auth/recover-password")
    def recover_password():
        data = validate("recoverPassword", request.get_json())
        complete_reset(
            data["email"], data["code"], data["password"], request.remote_addr or "unknown"
        )
        session.clear()
        return jsonify(ok=True)

    @app.post("/api/auth/reset-password")
    def reset_password():
        uid = session.get("reset_uid")
        endpoint_limits("password-reset", request.remote_addr or "unknown", uid)
        user = db().execute("SELECT auth_version FROM users WHERE id=?", (uid,)).fetchone()
        if not user or user["auth_version"] != session.get("reset_version"):
            raise AppError("Sign in again to reset your password.", 401)
        user = reset_admin_password(uid, validate("reset", request.get_json())["password"])
        establish_session(user)
        return jsonify(ok=True, redirect="/admin/overview")

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.put("/api/profile")
    @login_required
    def profile():
        d = request.get_json() or {}
        institution_id = integer(d.get("institution_id"), 1, 26)
        if institution_id != g.user["institution_id"]:
            institution = (
                db().execute("SELECT * FROM institutions WHERE id=?", (institution_id,)).fetchone()
            )
            validate_student_email(g.user["email"], institution)
        p = profile_data(d)
        execute(
            "UPDATE users SET name=?,programme=?,year=?,institution_id=?,profile=? WHERE id=?",
            (
                clean_text(d.get("name"), 80),
                clean_text(d.get("programme"), 100),
                integer(d.get("year"), 1, 7),
                integer(d.get("institution_id"), 1, 26),
                json.dumps(p),
                g.user["id"],
            ),
        )
        return jsonify(ok=True)

    @app.get("/api/peers")
    @login_required
    def peers():
        return jsonify(peers=recommendations(g.user["id"]))

    @app.get("/api/peers/<int:uid>")
    @login_required
    def peer(uid):
        u = (
            db()
            .execute(
                "SELECT u.*,i.name institution,i.acronym FROM users u JOIN institutions i ON i.id=u.institution_id WHERE u.id=? AND active=1 AND role='student' AND email_verified=1 AND status='ACTIVE'",
                (uid,),
            )
            .fetchone()
        )
        if not u:
            abort(404)
        return jsonify(user=public_user(u))

    @app.get("/api/activity")
    @login_required
    def activity():
        uid = g.user["id"]
        # Create each reminder once; use explicit South African time for local sessions.
        local_now = datetime.now(timezone(timedelta(hours=2))).replace(tzinfo=None)
        for s in rows(
            "SELECT * FROM study_sessions WHERE (creator=? OR peer=?) AND status='accepted'",
            (uid, uid),
        ):
            hours = (datetime.fromisoformat(s["starts"]) - local_now).total_seconds() / 3600
            message = f"Upcoming session #{s['id']}: {s['topic']} at {s['starts'].replace('T', ' ')} (SAST)."
            if 0 <= hours <= 24 and not rows(
                "SELECT id FROM notifications WHERE user_id=? AND message=?", (uid, message)
            ):
                notify(uid, message)
        return jsonify(
            connections=rows(
                "SELECT c.*,a.name sender_name,b.name receiver_name FROM connections c JOIN users a ON a.id=c.sender JOIN users b ON b.id=c.receiver WHERE sender=? OR receiver=? ORDER BY c.id DESC",
                (uid, uid),
            ),
            sessions=rows(
                "SELECT s.*,a.name creator_name,b.name peer_name,(SELECT id FROM feedback WHERE session_id=s.id AND author=?) feedback_id FROM study_sessions s JOIN users a ON a.id=s.creator JOIN users b ON b.id=s.peer WHERE creator=? OR peer=? ORDER BY starts",
                (uid, uid, uid),
            ),
            notifications=rows(
                "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (uid,)
            ),
        )

    @app.post("/api/connections")
    @login_required
    def connect():
        uid, target = (
            g.user["id"],
            integer((request.get_json() or {}).get("peer_id"), 1, 2147483647),
        )
        if target == uid or not rows(
            "SELECT id FROM users WHERE id=? AND active=1 AND role='student' AND email_verified=1 AND status='ACTIVE'",
            (target,),
        ):
            abort(400, description="Choose an active peer.")
        existing = rows(
            "SELECT * FROM connections WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)",
            (uid, target, target, uid),
        )
        if existing:
            if existing[0]["status"] != "declined":
                abort(409, description="A connection already exists.")
            execute(
                "UPDATE connections SET sender=?,receiver=?,status='pending',created=? WHERE id=?",
                (uid, target, now(), existing[0]["id"]),
            )
        else:
            execute(
                "INSERT INTO connections(sender,receiver,created) VALUES(?,?,?)",
                (uid, target, now()),
            )
        notify(target, g.user["name"] + " sent you a connection request.")
        return jsonify(ok=True), 201

    @app.patch("/api/connections/<int:cid>")
    @login_required
    def respond(cid):
        c = db().execute("SELECT * FROM connections WHERE id=?", (cid,)).fetchone()
        if not c:
            abort(404)
        if c["receiver"] != g.user["id"]:
            abort(403)
        status = (request.get_json() or {}).get("status")
        if status not in ["accepted", "declined"] or c["status"] != "pending":
            abort(400, description="This request cannot be updated.")
        execute("UPDATE connections SET status=? WHERE id=?", (status, cid))
        notify(c["sender"], g.user["name"] + " " + status + " your connection request.")
        return jsonify(ok=True)

    @app.post("/api/sessions")
    @login_required
    def arrange():
        d = request.get_json() or {}
        uid = g.user["id"]
        peer = integer(d.get("peer_id"), 1, 2147483647)
        if not rows(
            "SELECT id FROM connections WHERE status='accepted' AND ((sender=? AND receiver=?) OR (sender=? AND receiver=?))",
            (uid, peer, peer, uid),
        ):
            abort(403, description="Connect with this peer before arranging a session.")
        module, topic, location = (
            clean_text(d.get("module"), 80),
            clean_text(d.get("topic"), 150),
            clean_text(d.get("location"), 200),
        )
        if not rows("SELECT id FROM modules WHERE name=? AND active=1", (module,)):
            abort(400, description="Choose a listed module.")
        try:
            starts = datetime.fromisoformat(d.get("starts", ""))
        except (TypeError, ValueError):
            abort(400, description="Enter a valid session date and time.")
        if starts.tzinfo is not None or starts <= datetime.now(
            timezone(timedelta(hours=2))
        ).replace(tzinfo=None):
            abort(400, description="Choose a future local date and time (SAST).")
        duration = integer(d.get("duration"), 15, 240)
        for s in rows(
            "SELECT * FROM study_sessions WHERE status IN ('pending','accepted') AND (creator IN (?,?) OR peer IN (?,?))",
            (uid, peer, uid, peer),
        ):
            old = datetime.fromisoformat(s["starts"])
            if starts < old + timedelta(minutes=s["duration"]) and old < starts + timedelta(
                minutes=duration
            ):
                abort(409, description="A participant already has a session during this time.")
        execute(
            "INSERT INTO study_sessions(creator,peer,module,topic,starts,duration,location) VALUES(?,?,?,?,?,?,?)",
            (uid, peer, module, topic, starts.isoformat(timespec="minutes"), duration, location),
        )
        notify(peer, g.user["name"] + " invited you to study " + topic + ".")
        return jsonify(ok=True), 201

    @app.patch("/api/sessions/<int:sid>")
    @login_required
    def session_status(sid):
        s = db().execute("SELECT * FROM study_sessions WHERE id=?", (sid,)).fetchone()
        if not s:
            abort(404)
        uid = g.user["id"]
        status = (request.get_json() or {}).get("status")
        if uid not in [s["creator"], s["peer"]]:
            abort(403)
        allowed = (
            (status == "accepted" and s["status"] == "pending" and uid == s["peer"])
            or (status == "cancelled" and s["status"] in ["pending", "accepted"])
            or (
                status == "completed"
                and s["status"] == "accepted"
                and datetime.fromisoformat(s["starts"]) + timedelta(minutes=s["duration"])
                <= datetime.now(timezone(timedelta(hours=2))).replace(tzinfo=None)
            )
        )
        if not allowed:
            abort(400, description="This session cannot be changed to that status yet.")
        execute("UPDATE study_sessions SET status=? WHERE id=?", (status, sid))
        notify(
            s["peer"] if uid == s["creator"] else s["creator"],
            f"Session '{s['topic']}' was {status}.",
        )
        if status == "completed":
            for participant in [s["creator"], s["peer"]]:
                notify(participant, f"Leave feedback for completed session: {s['topic']}.")
        return jsonify(ok=True)

    @app.post("/api/sessions/<int:sid>/feedback")
    @login_required
    def feedback(sid):
        s = db().execute("SELECT * FROM study_sessions WHERE id=?", (sid,)).fetchone()
        if not s:
            abort(404)
        if g.user["id"] not in [s["creator"], s["peer"]]:
            abort(403)
        if s["status"] != "completed":
            abort(400, description="Feedback is available after a session is completed.")
        d = request.get_json() or {}
        rating = integer(d.get("rating"), 1, 5)
        if not isinstance(d.get("useful"), bool) or not isinstance(d.get("again"), bool):
            abort(400, description="Answer both feedback questions.")
        comments = d.get("comments", "")
        if not isinstance(comments, str) or len(comments) > 1000:
            abort(400, description="Keep comments under 1,000 characters.")
        try:
            execute(
                "INSERT INTO feedback(session_id,author,rating,useful,again,comments) VALUES(?,?,?,?,?,?)",
                (sid, g.user["id"], rating, int(d["useful"]), int(d["again"]), comments),
            )
        except sqlite3.IntegrityError:
            abort(409, description="You already reviewed this session.")
        return jsonify(ok=True), 201

    @app.post("/api/notifications/read")
    @login_required
    def mark_read():
        execute("UPDATE notifications SET seen=1 WHERE user_id=?", (g.user["id"],))
        return jsonify(ok=True)

    @app.cli.command("dispatch-announcements")
    def dispatch():
        from admin_service import dispatch_announcements

        print(f"Dispatched {dispatch_announcements()} announcements.")

    with app.app_context():
        db().executescript((BASE / "schema.sql").read_text())
        upgrade(db())
        db().executemany(
            "INSERT OR IGNORE INTO modules(name) VALUES(?)",
            [
                (m,)
                for m in [
                    "Computer Science",
                    "Mathematics",
                    "Statistics",
                    "Accounting",
                    "Economics",
                    "Physics",
                    "Biology",
                    "Academic Writing",
                    "Engineering",
                    "Psychology",
                ]
            ],
        )
        db().commit()

    return app
