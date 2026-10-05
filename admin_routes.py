from flask import Blueprint, g, jsonify, render_template, request

import admin_service as service
from access import admin_required
from database import db, rows
from errors import AppError
from validation import institution_records, validate

admin = Blueprint("admin", __name__)


@admin.get("/admin")
@admin.get("/admin/<path:page>")
@admin_required
def page(page: str = "overview"):
    if page not in [
        "overview",
        "students",
        "verifications",
        "institutions",
        "admins",
        "announcements",
        "audit",
    ]:
        raise AppError("Page not found.", 404)
    return render_template("admin.html")


@admin.get("/api/admin/overview")
@admin_required
def overview():
    return jsonify(service.overview())


@admin.get("/api/admin/students")
@admin_required
def students():
    institution = request.args.get("institution")
    try:
        iid = int(institution) if institution else None
    except ValueError:
        raise AppError("Invalid institution filter.") from None
    return jsonify(
        users=service.students(request.args.get("q", ""), iid, request.args.get("status", ""))
    )


@admin.get("/api/admin/students/<int:uid>")
@admin_required
def detail(uid: int):
    return jsonify(user=service.student_detail(uid))


@admin.post("/api/admin/students/<int:uid>")
@admin_required
def action(uid: int):
    service.student_action(
        g.user,
        uid,
        validate("studentAction", request.get_json())["action"],
        request.remote_addr or "unknown",
    )
    return jsonify(ok=True)


@admin.get("/api/admin/institutions")
@admin_required
def institutions():
    return jsonify(institutions=institution_records(db()))


@admin.put("/api/admin/institutions/<int:iid>")
@admin_required
def institution(iid: int):
    service.update_institution(g.user, iid, validate("institution", request.get_json()))
    return jsonify(ok=True)


@admin.get("/api/admin/admins")
@admin_required
def admins():
    return jsonify(users=service.admins(g.user))


@admin.put("/api/admin/admins/<int:uid>")
@admin_required
def update(uid: int):
    service.update_admin(g.user, uid, validate("adminAction", request.get_json()))
    return jsonify(ok=True)


@admin.get("/api/admin/announcements")
@admin_required
def announcements():
    return jsonify(
        announcements=rows(
            "SELECT id,title,body,institution_id,send_at,sent_at,created FROM announcements ORDER BY id DESC"
        )
    )


@admin.post("/api/admin/announcements")
@admin_required
def announce():
    service.create_announcement(g.user, validate("announcement", request.get_json()))
    return jsonify(ok=True), 201


@admin.get("/api/admin/audit")
@admin_required
def audit():
    return jsonify(
        entries=rows(
            "SELECT actor_name,action,target,created,details FROM audit_log ORDER BY id DESC LIMIT 500"
        )
    )
