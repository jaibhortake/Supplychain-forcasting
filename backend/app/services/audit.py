"""Audit trail + data-version bookkeeping. Call `record()` for every user-visible write."""

import json

from sqlalchemy.orm import Session

from app.models import AuditLog, DataVersion


def current_version(session: Session) -> int:
    row = session.get(DataVersion, 1)
    return row.version if row else 0


def bump_version(session: Session) -> None:
    row = session.get(DataVersion, 1)
    if row is None:
        session.add(DataVersion(id=1, version=1))
    else:
        row.version += 1


def record(
    session: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | int,
    summary: str,
    details: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            summary=summary,
            details=json.dumps(details or {}, default=str),
        )
    )
    bump_version(session)
