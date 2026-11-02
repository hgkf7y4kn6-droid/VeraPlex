import uuid
from datetime import date, timedelta

from fastapi import HTTPException
import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.core.security import Principal
from app.modules.audit import service as audit
from app.modules.quality import rules
from app.modules.quality.models import Capa, Deviation, IdempotencyKey, Investigation
from app.modules.records import service as records


def recurrence_count(db: Session, tenant_id: uuid.UUID, equipment_id: str | None) -> int:
    if not equipment_id:
        return 0
    since = utcnow() - timedelta(days=settings.recurrence_window_days)
    return db.scalar(select(func.count()).select_from(Deviation).where(
        Deviation.tenant_id == tenant_id, Deviation.equipment_id == equipment_id, Deviation.opened_at >= since
    )) or 0


def raise_deviation(db: Session, p: Principal, content: dict) -> Deviation:
    r = records.create(db, p, "deviation", "open", content, "deviation raised")
    d = Deviation(
        record_id=r.id, tenant_id=p.tenant_id, equipment_id=content.get("equipment_id"),
        batch_id=content.get("batch_id"), opened_at=r.created_at,
    )
    db.add(d)
    db.flush()
    if recurrence_count(db, p.tenant_id, d.equipment_id) >= settings.recurrence_threshold:
        d.recurring = True
        audit.record_event(
            db, tenant_id=p.tenant_id, actor_id=None, actor_kind="system", action="deviation.recurrence_flagged",
            entity_type="deviation", entity_id=r.id,
            new={"equipment_id": d.equipment_id, "window_days": settings.recurrence_window_days},
            reason=f">= {settings.recurrence_threshold} deviations on same equipment (deterministic rule)",
        )
    return d


def get_deviation(db: Session, p: Principal, record_id: uuid.UUID) -> Deviation:
    d = db.scalars(select(Deviation).where(Deviation.record_id == record_id, Deviation.tenant_id == p.tenant_id)).first()
    if not d:
        raise HTTPException(404, "not found")
    return d


def triage(db: Session, p: Principal, d: Deviation, sev: int, occ: int, det: int,
           owner_id: uuid.UUID, due: date, reason: str):
    r = records.get_record(db, p, d.record_id, "deviation")
    try:
        score, cls = rules.risk_score(sev, occ, det)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    v = records.current_version(db, r)
    content = {**v.content, "triage": {
        "severity": sev, "occurrence": occ, "detectability": det, "risk_score": score, "classification": cls,
        "owner_id": str(owner_id), "due_date": due.isoformat(),
    }}
    records.edit_draft(db, p, r, content, reason or "triage")
    d.risk_score, d.classification, d.owner_id, d.due_date = score, cls, owner_id, due
    records.transition(db, p, r, "triaged", rules.DEVIATION, reason or "triage complete")
    return d


def start_investigation(db: Session, p: Principal, d: Deviation, reason: str) -> Investigation:
    r = records.get_record(db, p, d.record_id, "deviation")
    records.transition(db, p, r, "investigation", rules.DEVIATION, reason)
    inv_rec = records.create(db, p, "investigation", "draft", {"five_whys": [], "root_cause": None}, "investigation opened")
    inv = Investigation(record_id=inv_rec.id, tenant_id=p.tenant_id, deviation_id=d.record_id)
    db.add(inv)
    db.flush()
    return inv


def propose_capa(db: Session, p: Principal, d: Deviation, content: dict) -> Capa:
    dev_rec = records.get_record(db, p, d.record_id, "deviation")
    if dev_rec.state != "investigation":
        raise HTTPException(409, "a CAPA can only be proposed from an open investigation")
    r = records.create(db, p, "capa", "draft", content, "CAPA proposed")
    capa = Capa(record_id=r.id, tenant_id=p.tenant_id, deviation_id=d.record_id)
    db.add(capa)
    records.transition(db, p, dev_rec, "capa_proposed", rules.DEVIATION, "CAPA proposed")
    db.flush()
    return capa


def capa_transition(db: Session, p: Principal, capa: Capa, to: str, reason: str):
    r = records.get_record(db, p, capa.record_id, "capa")
    if to == "approved":
        v = records.current_version(db, r)
        roles = {s.signer_role for s in records.signatures_for(db, v) if s.meaning == "approved"}
        missing = rules.REQUIRED_CAPA_APPROVER_ROLES - roles
        if missing:
            raise HTTPException(409, f"missing approval signatures from: {sorted(missing)}")
    records.transition(db, p, r, to, rules.CAPA, reason)
    if to == "approved":
        capa.approved_at = utcnow()
        capa.effectiveness_due = capa.approved_at.date() + timedelta(days=settings.effectiveness_check_days)
        audit.record_event(
            db, tenant_id=p.tenant_id, actor_id=None, actor_kind="system", action="capa.effectiveness_scheduled",
            entity_type="capa", entity_id=r.id, new={"due": capa.effectiveness_due.isoformat()},
            reason="scheduled automatically on approval",
        )
    return r


def raise_deviation_idempotent(db: Session, p: Principal, content: dict, key: str | None) -> tuple[Deviation, bool]:
    """Returns (deviation, created). A replay of the same key+payload returns the original."""
    if not key:
        return raise_deviation(db, p, content), True
    if not 8 <= len(key) <= 128:
        raise HTTPException(422, "Idempotency-Key must be 8-128 characters")
    h = hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()
    try:
        with db.begin_nested():
            row = IdempotencyKey(tenant_id=p.tenant_id, user_id=p.user_id, key=key, request_hash=h)
            db.add(row)
            db.flush()
    except IntegrityError:
        row = db.scalars(select(IdempotencyKey).where(
            IdempotencyKey.tenant_id == p.tenant_id, IdempotencyKey.user_id == p.user_id, IdempotencyKey.key == key)).one()
        if row.request_hash != h:
            raise HTTPException(422, "Idempotency-Key was already used with a different payload")
        return get_deviation(db, p, row.record_id), False
    d = raise_deviation(db, p, content)
    row.record_id = d.record_id
    return d, True
