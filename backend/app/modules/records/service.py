import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit import service as audit
from app.modules.identity.principal import PermissionDenied, Principal
from app.modules.records.models import Record, RecordVersion

# Allowed transitions. Approval and retirement need signatures (enforced by the signatures module).
TRANSITIONS = {
    "draft": {"in_review"},
    "in_review": {"draft", "approved"},
    "approved": {"retired"},
    "retired": set(),
}


class InvalidTransition(Exception):
    pass


def content_hash(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def get(session: Session, actor: Principal, record_id: str) -> Record:
    rec = session.get(Record, record_id)
    # Same error for "missing" and "other tenant" so existence cannot be inferred.
    if rec is None or rec.tenant_id != actor.tenant_id:
        raise LookupError("record not found")
    return rec


def get_version(session: Session, record: Record, version_no: int | None = None) -> RecordVersion:
    return session.scalars(
        select(RecordVersion).where(
            RecordVersion.record_id == record.id,
            RecordVersion.version_no == (version_no or record.current_version),
        )
    ).one()


def _add_version(session, actor, record, version_no, content) -> RecordVersion:
    v = RecordVersion(
        id=str(uuid.uuid4()), tenant_id=actor.tenant_id, record_id=record.id,
        version_no=version_no, content=content, content_hash=content_hash(content),
        author_id=actor.user_id, created_at=datetime.now(UTC),
    )
    session.add(v)
    return v


def create(session: Session, actor: Principal, type_: str, content: dict) -> Record:
    rec = Record(id=str(uuid.uuid4()), tenant_id=actor.tenant_id, type=type_,
                 state="draft", current_version=1)
    session.add(rec)
    _add_version(session, actor, rec, 1, content)
    audit.append(session, actor, action="record.create", entity_type=type_, entity_id=rec.id,
                 new_value={"state": "draft", "version": 1})
    return rec


def edit_draft(session: Session, actor: Principal, record_id: str, content: dict, reason: str) -> Record:
    """Approved records are immutable; only drafts are edited in place."""
    rec = get(session, actor, record_id)
    if rec.state != "draft":
        raise InvalidTransition("only draft records can be edited; use revise() for approved ones")
    v = get_version(session, rec)
    old = v.content
    v.content, v.content_hash = content, content_hash(content)
    audit.append(session, actor, action="record.edit", entity_type=rec.type, entity_id=rec.id,
                 old_value=old, new_value=content, reason=reason)
    return rec


def revise(session: Session, actor: Principal, record_id: str, content: dict, reason: str) -> Record:
    """Change control: an approved record gets a new draft version; the old one is untouched."""
    rec = get(session, actor, record_id)
    if rec.state != "approved":
        raise InvalidTransition("only approved records are revised")
    rec.current_version += 1
    rec.state = "draft"
    _add_version(session, actor, rec, rec.current_version, content)
    audit.append(session, actor, action="record.revise", entity_type=rec.type, entity_id=rec.id,
                 old_value={"state": "approved"}, new_value={"state": "draft", "version": rec.current_version},
                 reason=reason)
    return rec


SIGNED_STATES = {"approved", "retired"}


def transition(session: Session, actor: Principal, record_id: str, to_state: str, reason: str) -> Record:
    """Unsigned transitions only. Approval and retirement go through signatures.approve()."""
    if to_state in SIGNED_STATES:
        raise InvalidTransition(f"'{to_state}' requires an e-signature; use the signatures module")
    return _transition(session, actor, record_id, to_state, reason)


def apply_signed_transition(session, actor, record_id, to_state, reason) -> Record:
    """Called by the signatures module after a valid signature has been recorded."""
    return _transition(session, actor, record_id, to_state, reason)


def _transition(session, actor, record_id, to_state, reason) -> Record:
    actor.forbid_ai("change record state")
    rec = get(session, actor, record_id)
    if to_state not in TRANSITIONS[rec.state]:
        raise InvalidTransition(f"{rec.state} -> {to_state} not allowed")
    if not reason:
        raise InvalidTransition("a reason is required for every state change")
    old = rec.state
    rec.state = to_state
    audit.append(session, actor, action="record.transition", entity_type=rec.type, entity_id=rec.id,
                 old_value={"state": old}, new_value={"state": to_state}, reason=reason)
    return rec


__all__ = ["PermissionDenied", "apply_signed_transition", "create", "edit_draft", "get_version", "revise", "transition"]
