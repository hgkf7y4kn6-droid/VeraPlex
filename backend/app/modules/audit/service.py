import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.identity.principal import Principal

GENESIS = "0" * 64


def _digest(prev_hash: str, fields: dict) -> str:
    body = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite drops tzinfo


def _fields(e: AuditEvent) -> dict:
    return {
        "tenant_id": e.tenant_id, "seq": e.seq, "occurred_at": _utc(e.occurred_at).isoformat(),
        "actor_id": e.actor_id, "actor_kind": e.actor_kind, "action": e.action,
        "entity_type": e.entity_type, "entity_id": e.entity_id,
        "old_value": e.old_value, "new_value": e.new_value, "reason": e.reason,
    }


def append(
    session: Session, actor: Principal, *, action: str, entity_type: str, entity_id: str,
    old_value: dict | None = None, new_value: dict | None = None, reason: str | None = None,
) -> AuditEvent:
    last = session.scalars(
        select(AuditEvent).where(AuditEvent.tenant_id == actor.tenant_id)
        .order_by(AuditEvent.seq.desc()).limit(1)
    ).first()
    event = AuditEvent(
        tenant_id=actor.tenant_id, seq=(last.seq + 1) if last else 1,
        occurred_at=datetime.now(UTC), actor_id=actor.user_id, actor_kind=actor.kind,
        action=action, entity_type=entity_type, entity_id=entity_id,
        old_value=old_value, new_value=new_value, reason=reason,
        prev_hash=last.hash if last else GENESIS, hash="",
    )
    event.hash = _digest(event.prev_hash, _fields(event))
    session.add(event)
    session.flush()
    return event


def verify_chain(session: Session, tenant_id: str) -> list[int]:
    """Return the seq numbers where the chain is broken (empty list = intact)."""
    broken, prev = [], GENESIS
    for e in session.scalars(
        select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.seq)
    ):
        if e.prev_hash != prev or e.hash != _digest(prev, _fields(e)):
            broken.append(e.seq)
        prev = e.hash
    return broken
