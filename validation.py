import json
import re
from pathlib import Path
from typing import Mapping

from jsonschema import Draft202012Validator

from errors import AppError

SCHEMAS: dict = json.loads((Path(__file__).parent / "schemas.json").read_text())


def validate(name: str, data: object) -> dict:
    errors = list(Draft202012Validator(SCHEMAS[name]).iter_errors(data))
    if errors:
        field = str(next(iter(errors[0].path), "")) or None
        raise AppError("Check the highlighted field and try again.", 400, field)
    assert isinstance(data, dict)
    return data


def institution_records(connection) -> list[dict]:
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "shortName": r["acronym"],
            "acronym": r["acronym"],
            "studentEmailDomain": r["student_email_domain"],
            "isActive": bool(r["is_active"]),
        }
        for r in connection.execute("SELECT * FROM institutions ORDER BY name")
    ]


def validate_student_email(email: str, institution: Mapping) -> str:
    normalized = email.strip().lower()
    if not institution["is_active"]:
        raise AppError("This institution is not accepting registrations.", field="institution_id")
    if not re.fullmatch(
        r"[a-zA-Z0-9._%+-]+@" + re.escape(institution["student_email_domain"]), normalized
    ):
        raise AppError(
            "Use the official student email for your selected institution.", field="email"
        )
    return normalized
