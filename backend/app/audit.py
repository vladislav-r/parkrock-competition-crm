import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import Admin, AuditLog


def json_value(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))


def write_audit(
    db: Session,
    *,
    actor: Admin | None,
    action: str,
    target_type: str,
    target_id: str = "",
    old_value: Any = None,
    new_value: Any = None,
    result: str = "success",
    audit_id: uuid.UUID | None = None,
) -> AuditLog:
    entry = AuditLog(
        id=audit_id or uuid.uuid4(), actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else "", actor_role=actor.role.value if actor else "",
        action=action, target_type=target_type, target_id=target_id,
        old_value_json=json_value(old_value), new_value_json=json_value(new_value), result=result,
    )
    db.add(entry)
    return entry
