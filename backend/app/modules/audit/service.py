import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.modules.audit.models import AuditEvent

GENESIS = "0" * 64


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, e: AuditEvent) -> str:
    body = {
        "tenant_id": str(e.tenant_id), "seq": e.seq, "occurred_at": e.occurred_at.isoformat(),
        "actor_id": str(e.actor_id) if e.actor_id else None, "actor_kind": e.actor_kind,
        "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id,
        "old_value": e.old_value, "new_value": e.new_value, "reason": e.reason,
    }
    return hashlib.sha256((prev_hash + _canonical(body)).encode()).hexdigest()


def record_event(
    db: Session, *, tenant_id: uuid.UUID, actor_id: uuid.UUID | None, actor_kind: str, action: str,
    entity_type: str, entity_id: Any, old: dict | None = None, new: dict | None = None,
    reason: str | None = None,
) -> AuditEvent:
    """Written in the caller's transaction, so a business write and its audit row commit together."""
    if db.get_bind().dialect.name == "postgresql":  # serialise chain writers per tenant
        db.execute(text("select pg_advisory_xact_lock(hashtext(:t))"), {"t": str(tenant_id)})
    last = db.execute(
        select(AuditEvent.seq, AuditEvent.hash).where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.seq.desc()).limit(1)
    ).first()
    seq, prev = (last.seq + 1, last.hash) if last else (1, GENESIS)
    ev = AuditEvent(
        tenant_id=tenant_id, seq=seq, occurred_at=utcnow(), actor_id=actor_id, actor_kind=actor_kind,
        action=action, entity_type=entity_type, entity_id=str(entity_id), old_value=old, new_value=new,
        reason=reason, prev_hash=prev, hash="",
    )
    ev.hash = compute_hash(prev, ev)
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session, tenant_id: uuid.UUID) -> dict:
    """Nightly job entry point. Returns the first break, if any."""
    prev, expected_seq = GENESIS, 1
    rows = db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.seq))
    n = 0
    for e in rows:
        n += 1
        if e.seq != expected_seq:
            return {"ok": False, "checked": n, "break_at_seq": expected_seq, "reason": "sequence gap"}
        if e.prev_hash != prev or compute_hash(prev, e) != e.hash:
            return {"ok": False, "checked": n, "break_at_seq": e.seq, "reason": "hash mismatch"}
        prev, expected_seq = e.hash, expected_seq + 1
    return {"ok": True, "checked": n, "break_at_seq": None, "reason": None}


def count(db: Session, tenant_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.tenant_id == tenant_id)) or 0
