"""Controlled-record kernel: versions never overwrite once locked; signatures bind to a content hash."""
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core import providers
from app.core.config import settings
from app.core.security import Principal
from app.modules.audit import service as audit
from app.modules.records.models import (
    ReauthEvent, Record, RecordStateTransition, RecordVersion, Signature,
)

MEANINGS = {"authored", "reviewed", "approved", "verified"}


@dataclass(frozen=True)
class StateMachine:
    transitions: dict[str, set[str]]
    lock_on_enter: set[str] = field(default_factory=set)


def content_hash(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def get_record(db: Session, p: Principal, record_id: uuid.UUID, rtype: str | None = None) -> Record:
    """Tenant-scoped fetch; another tenant's record is indistinguishable from a missing one."""
    r = db.scalars(select(Record).where(Record.id == record_id, Record.tenant_id == p.tenant_id)).first()
    if not r or (rtype and r.type != rtype):
        raise HTTPException(404, "not found")
    return r


def current_version(db: Session, r: Record) -> RecordVersion:
    return db.scalars(
        select(RecordVersion).where(RecordVersion.record_id == r.id, RecordVersion.version_no == r.current_version_no)
    ).one()


def signatures_for(db: Session, v: RecordVersion) -> list[Signature]:
    return list(db.scalars(select(Signature).where(Signature.record_version_id == v.id).order_by(Signature.signed_at)))


def create(db: Session, p: Principal, rtype: str, state: str, content: dict, reason: str) -> Record:
    now = utcnow()
    r = Record(tenant_id=p.tenant_id, type=rtype, state=state, created_by=p.user_id, created_at=now)
    db.add(r)
    db.flush()
    db.add(RecordVersion(
        tenant_id=p.tenant_id, record_id=r.id, version_no=1, content=content,
        content_hash=content_hash(content), author_id=p.user_id, created_at=now,
    ))
    audit.record_event(
        db, tenant_id=p.tenant_id, actor_id=p.user_id, actor_kind=p.kind, action=f"{rtype}.create",
        entity_type=rtype, entity_id=r.id, new={"state": state, "content_hash": content_hash(content)}, reason=reason,
    )
    return r


def edit_draft(db: Session, p: Principal, r: Record, content: dict, reason: str) -> RecordVersion:
    """In-place edit allowed only while the version is unlocked and unsigned."""
    v = current_version(db, r)
    if v.locked or signatures_for(db, v):
        raise HTTPException(409, "version is locked; create a new version through change control")
    old = {"content_hash": v.content_hash}
    v.content, v.content_hash, v.author_id = content, content_hash(content), p.user_id
    audit.record_event(
        db, tenant_id=p.tenant_id, actor_id=p.user_id, actor_kind=p.kind, action=f"{r.type}.edit",
        entity_type=r.type, entity_id=r.id, old=old, new={"content_hash": v.content_hash}, reason=reason,
    )
    return v


def new_version(db: Session, p: Principal, r: Record, content: dict, reason: str) -> RecordVersion:
    old = current_version(db, r)
    if not old.locked:
        raise HTTPException(409, "current version is still a draft; edit it instead")
    r.current_version_no += 1
    v = RecordVersion(
        tenant_id=p.tenant_id, record_id=r.id, version_no=r.current_version_no, content=content,
        content_hash=content_hash(content), author_id=p.user_id, created_at=utcnow(),
    )
    db.add(v)
    db.flush()
    audit.record_event(
        db, tenant_id=p.tenant_id, actor_id=p.user_id, actor_kind=p.kind, action=f"{r.type}.new_version",
        entity_type=r.type, entity_id=r.id, old={"version": old.version_no, "content_hash": old.content_hash},
        new={"version": v.version_no, "content_hash": v.content_hash}, reason=reason,
    )
    return v


def transition(db: Session, p: Principal, r: Record, to: str, machine: StateMachine, reason: str) -> Record:
    if not reason.strip():
        raise HTTPException(422, "a reason is required for every state change")
    if to not in machine.transitions.get(r.state, set()):
        raise HTTPException(409, f"illegal transition {r.state} -> {to}")
    frm, r.state = r.state, to
    if to in machine.lock_on_enter:
        current_version(db, r).locked = True
    db.add(RecordStateTransition(
        tenant_id=p.tenant_id, record_id=r.id, from_state=frm, to_state=to, actor_id=p.user_id,
        reason=reason, at=utcnow(),
    ))
    audit.record_event(
        db, tenant_id=p.tenant_id, actor_id=p.user_id, actor_kind=p.kind, action=f"{r.type}.transition",
        entity_type=r.type, entity_id=r.id, old={"state": frm}, new={"state": to}, reason=reason,
    )
    return r


def _consume_reauth(db: Session, p: Principal, reauth_token: str) -> ReauthEvent:
    """Re-authentication at the moment of signing: the user must have *proved identity* recently
    (Supabase `amr` timestamp, not merely a refreshed token), as the same subject, usable once."""
    try:
        c = providers.auth_provider.verify(reauth_token)
    except providers.AuthError as exc:
        raise HTTPException(401, "re-authentication failed") from exc
    if c.sub != str(p.user_id):
        raise HTTPException(401, "re-authentication does not match the signer")
    if time.time() - c.authenticated_at > settings.reauth_max_age_seconds:
        raise HTTPException(401, "re-authentication is too old; sign in again")
    if db.scalars(select(ReauthEvent).where(ReauthEvent.jti == c.token_id)).first():
        raise HTTPException(401, "re-authentication token already used")
    ev = ReauthEvent(tenant_id=p.tenant_id, user_id=p.user_id, jti=c.token_id, at=utcnow())
    db.add(ev)
    db.flush()
    return ev


def sign(db: Session, p: Principal, r: Record, meaning: str, reauth_token: str) -> Signature:
    if p.kind != "human":
        raise HTTPException(403, "only a human principal can sign")
    if meaning not in MEANINGS:
        raise HTTPException(422, f"meaning must be one of {sorted(MEANINGS)}")
    v = current_version(db, r)
    if content_hash(v.content) != v.content_hash:
        raise HTTPException(409, "stored content does not match its hash; refusing to sign")
    if meaning == "approved" and v.author_id == p.user_id:
        raise HTTPException(403, "segregation of duties: the author cannot approve their own record")
    if db.scalars(select(Signature).where(
        Signature.record_version_id == v.id, Signature.signer_id == p.user_id, Signature.meaning == meaning
    )).first():
        raise HTTPException(409, "already signed with this meaning")
    ev = _consume_reauth(db, p, reauth_token)
    v.locked = True
    s = Signature(
        tenant_id=p.tenant_id, record_version_id=v.id, signer_id=p.user_id, signer_name=p.name,
        signer_role=p.role, meaning=meaning, signed_at=utcnow(), content_hash=v.content_hash, reauth_event_id=ev.id,
    )
    db.add(s)
    db.flush()
    audit.record_event(
        db, tenant_id=p.tenant_id, actor_id=p.user_id, actor_kind=p.kind, action=f"{r.type}.sign",
        entity_type=r.type, entity_id=r.id,
        new={"meaning": meaning, "version": v.version_no, "content_hash": v.content_hash, "signer_role": p.role},
        reason=f"signed: {meaning}",
    )
    return s


def manifestation(s: Signature) -> dict:
    """What every view and export must render next to a signed record."""
    return {
        "signer": s.signer_name, "role": s.signer_role, "meaning": s.meaning,
        "signed_at_utc": s.signed_at.isoformat() + "Z", "content_hash": s.content_hash,
    }
