import pytest
from sqlalchemy import text

from app.modules.audit import service as audit
from app.modules.audit.models import AuditEvent
from app.modules.identity.principal import PermissionDenied
from app.modules.records import service as records
from app.modules.signatures import service as sigs
from tests.conftest import P

alice, bob, bot = P("alice"), P("bob"), P("ai-1", kind="ai")


def test_audit_chain_detects_tampering(session):
    rec = records.create(session, alice, "capa", {"a": 1})
    records.edit_draft(session, alice, rec.id, {"a": 2}, "fix typo")
    assert audit.verify_chain(session, "t1") == []
    session.execute(text("UPDATE audit_event SET reason='x' WHERE seq=2"))  # raw SQL bypasses ORM guard
    assert audit.verify_chain(session, "t1") == [2]


def test_audit_orm_update_blocked(session):
    records.create(session, alice, "capa", {})
    ev = session.query(AuditEvent).first()
    ev.reason = "changed"
    with pytest.raises(RuntimeError):
        session.flush()


def test_tenant_isolation(session):
    rec = records.create(session, alice, "capa", {})
    with pytest.raises(LookupError):
        records.get(session, P("eve", tenant="t2"), rec.id)


def test_approval_needs_signature_and_segregation(session, auth):
    rec = records.create(session, alice, "capa", {"x": 1})
    records.transition(session, alice, rec.id, "in_review", "ready")
    with pytest.raises(records.InvalidTransition):
        records.transition(session, bob, rec.id, "approved", "skip signature")
    with pytest.raises(PermissionDenied):
        sigs.approve(session, auth, alice, "Alice", rec.id, "ok", "self-approve")
    with pytest.raises(PermissionError):
        sigs.approve(session, auth, bob, "Bob", rec.id, "bad", "wrong password")
    sigs.approve(session, auth, bob, "Bob", rec.id, "ok", "approved by QA")
    assert records.get(session, bob, rec.id).state == "approved"
    assert audit.verify_chain(session, "t1") == []


def test_signature_bound_to_content_and_approved_immutable(session, auth):
    rec = records.create(session, alice, "sop", {"v": 1})
    records.transition(session, alice, rec.id, "in_review", "ready")
    sigs.approve(session, auth, bob, "Bob", rec.id, "ok", "ok")
    v1 = records.get_version(session, rec)
    with pytest.raises(records.InvalidTransition):
        records.edit_draft(session, alice, rec.id, {"v": 99}, "sneaky")
    records.revise(session, alice, rec.id, {"v": 2}, "change control CC-1")
    assert rec.current_version == 2 and v1.content == {"v": 1}
    sig = sigs.for_version(session, v1.id)[0]
    assert "INVALID" not in sigs.manifestation(session, sig)
    v1.content_hash = "tampered"
    assert "INVALID" in sigs.manifestation(session, sig)


def test_ai_principal_cannot_approve_sign_or_transition(session, auth):
    rec = records.create(session, bot, "capa", {})  # AI may draft
    with pytest.raises(PermissionDenied):
        sigs.sign(session, auth, bot, "AI", rec.id, "reviewed", "ok")
    with pytest.raises(PermissionDenied):
        sigs.approve(session, auth, bot, "AI", rec.id, "ok", "r")
    with pytest.raises(PermissionDenied):
        records.transition(session, bot, rec.id, "in_review", "r")
