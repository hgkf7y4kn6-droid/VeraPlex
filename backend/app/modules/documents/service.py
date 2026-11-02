"""SOP control: revisions are controlled records; only approved revisions become effective;
going effective supersedes the prior revision and assigns training."""
import uuid
from collections.abc import Callable
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.core.security import Principal
from app.modules.audit import service as audit
from app.modules.documents.models import Acknowledgment, Sop, SopRevision, TrainingAssignment
from app.modules.identity.models import Membership, User
from app.modules.records import service as records
from app.modules.records.service import StateMachine

SOP_REVISION = StateMachine(
    transitions={
        "draft": {"in_review"},
        "in_review": {"approved"},
        "approved": {"effective"},
        "effective": {"superseded"},
    },
    lock_on_enter={"in_review", "approved", "effective", "superseded"},
)
OPEN_STATES = ("draft", "in_review", "approved")
HUMAN_ROLES_DEFAULT = ["operator", "investigator", "qa", "area_owner"]

# Dependency inversion: higher modules (quality change control) react to events without
# the documents module importing them.
_effective_hooks: list[Callable[[Session, Principal, SopRevision], None]] = []


def on_revision_effective(fn):
    _effective_hooks.append(fn)
    return fn


def get_sop(db: Session, p: Principal, sop_id: uuid.UUID) -> Sop:
    s = db.scalars(select(Sop).where(Sop.id == sop_id, Sop.tenant_id == p.tenant_id)).first()
    if not s:
        raise HTTPException(404, "not found")
    return s


def get_revision(db: Session, p: Principal, rid: uuid.UUID) -> SopRevision:
    r = db.scalars(select(SopRevision).where(SopRevision.record_id == rid, SopRevision.tenant_id == p.tenant_id)).first()
    if not r:
        raise HTTPException(404, "not found")
    return r


def create_sop(db: Session, p: Principal, doc_number: str, title: str, body: str, interval: int,
               training_roles: list[str] | None) -> tuple[Sop, SopRevision]:
    if db.scalars(select(Sop).where(Sop.tenant_id == p.tenant_id, Sop.doc_number == doc_number)).first():
        raise HTTPException(409, "document number already exists")
    sop = Sop(tenant_id=p.tenant_id, doc_number=doc_number, title=title, review_interval_months=interval)
    db.add(sop)
    db.flush()
    content = {"doc_number": doc_number, "title": title, "body": body,
               "training_roles": training_roles or HUMAN_ROLES_DEFAULT, "change_summary": "initial release"}
    return sop, _new_revision(db, p, sop, 1, content, None)


def _new_revision(db, p, sop, no, content, reason) -> SopRevision:
    rec = records.create(db, p, "sop_revision", "draft", content, reason or "SOP drafted")
    rev = SopRevision(record_id=rec.id, tenant_id=p.tenant_id, sop_id=sop.id, revision_no=no)
    db.add(rev)
    db.flush()
    return rev


def open_revision(db: Session, p: Principal, sop: Sop, body: str, change_summary: str) -> SopRevision:
    """New draft revision based on the current effective one. One open revision at a time."""
    open_ = db.scalars(select(SopRevision).join(
        records.Record, records.Record.id == SopRevision.record_id
    ).where(SopRevision.sop_id == sop.id, records.Record.state.in_(OPEN_STATES))).first()
    if open_:
        raise HTTPException(409, "a revision is already in progress for this SOP")
    if not sop.effective_revision_id:
        raise HTTPException(409, "SOP has no effective revision to revise")
    base = records.get_record(db, p, sop.effective_revision_id)
    content = {**records.current_version(db, base).content, "body": body, "change_summary": change_summary}
    n = 1 + max(db.scalars(select(SopRevision.revision_no).where(SopRevision.sop_id == sop.id)))
    return _new_revision(db, p, sop, n, content, f"revision {n}: {change_summary}")


def submit_for_review(db: Session, p: Principal, rev: SopRevision, reason: str):
    records.transition(db, p, records.get_record(db, p, rev.record_id, "sop_revision"), "in_review", SOP_REVISION, reason)


def approve(db: Session, p: Principal, rev: SopRevision, reason: str):
    r = records.get_record(db, p, rev.record_id, "sop_revision")
    v = records.current_version(db, r)
    sigs = records.signatures_for(db, v)
    reviewed = [s for s in sigs if s.meaning == "reviewed" and s.signer_id != v.author_id]
    approved = [s for s in sigs if s.meaning == "approved"]
    if not reviewed:
        raise HTTPException(409, "needs a 'reviewed' signature from someone other than the author")
    if not approved:
        raise HTTPException(409, "needs an 'approved' signature")
    if {s.signer_id for s in approved} & {s.signer_id for s in reviewed}:
        raise HTTPException(409, "reviewer and approver must be different people")
    records.transition(db, p, r, "approved", SOP_REVISION, reason)


def make_effective(db: Session, p: Principal, rev: SopRevision) -> list[TrainingAssignment]:
    r = records.get_record(db, p, rev.record_id, "sop_revision")
    sop = get_sop(db, p, rev.sop_id)
    today = utcnow().date()
    # supersede the previous effective revision first
    if sop.effective_revision_id:
        prev = records.get_record(db, p, sop.effective_revision_id)
        records.transition(db, p, prev, "superseded", SOP_REVISION, f"superseded by revision {rev.revision_no}")
        for a in db.scalars(select(TrainingAssignment).where(
            TrainingAssignment.revision_id == prev.id, TrainingAssignment.status == "assigned")):
            a.status = "superseded"
    records.transition(db, p, r, "effective", SOP_REVISION, f"revision {rev.revision_no} effective")
    rev.effective_date = today
    rev.review_due = _add_months(today, sop.review_interval_months)
    sop.effective_revision_id = rev.record_id
    content = records.current_version(db, r).content
    roles = content.get("training_roles") or HUMAN_ROLES_DEFAULT
    users = db.scalars(select(User).join(Membership, Membership.user_id == User.id).where(
        Membership.tenant_id == p.tenant_id, Membership.active.is_(True), User.active.is_(True),
        User.kind == "human", Membership.role.in_(roles)).distinct())
    out = []
    for u in users:
        a = TrainingAssignment(tenant_id=p.tenant_id, revision_id=rev.record_id, user_id=u.id,
                               due_date=today + timedelta(days=settings.training_due_days), assigned_at=utcnow())
        db.add(a)
        out.append(a)
    db.flush()
    audit.record_event(
        db, tenant_id=p.tenant_id, actor_id=None, actor_kind="system", action="sop.training_assigned",
        entity_type="sop_revision", entity_id=rev.record_id, new={"assigned": len(out), "roles": roles},
        reason="assigned automatically when revision became effective",
    )
    for hook in _effective_hooks:
        hook(db, p, rev)
    return out


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last))


def acknowledge(db: Session, p: Principal, assignment_id: uuid.UUID, reauth_token: str) -> Acknowledgment:
    a = db.scalars(select(TrainingAssignment).where(
        TrainingAssignment.id == assignment_id, TrainingAssignment.tenant_id == p.tenant_id,
        TrainingAssignment.user_id == p.user_id)).first()
    if not a:
        raise HTTPException(404, "not found")
    if a.status == "superseded":
        raise HTTPException(409, "this revision has been superseded; train on the current revision")
    if a.status == "acknowledged":
        raise HTTPException(409, "already acknowledged")
    r = records.get_record(db, p, a.revision_id)
    if r.state != "effective":
        raise HTTPException(409, "revision is not effective")
    ev = records.consume_reauth(db, p, reauth_token)
    ack = Acknowledgment(
        tenant_id=p.tenant_id, assignment_id=a.id, user_id=p.user_id, user_name=p.name,
        content_hash=records.current_version(db, r).content_hash, acknowledged_at=utcnow(), reauth_event_id=ev.id,
    )
    db.add(ack)
    a.status = "acknowledged"
    db.flush()
    audit.record_event(
        db, tenant_id=p.tenant_id, actor_id=p.user_id, actor_kind=p.kind, action="training.acknowledge",
        entity_type="training_assignment", entity_id=a.id, new={"revision": str(a.revision_id), "content_hash": ack.content_hash},
        reason="read and understood",
    )
    return ack


def reminders(db: Session, tenant_id: uuid.UUID, today: date, horizon_days: int = 60) -> dict:
    """Entry point for the scheduled job (Celery later): SOP reviews coming due + overdue training."""
    horizon = today + timedelta(days=horizon_days)
    sops = db.execute(select(Sop, SopRevision).join(SopRevision, SopRevision.record_id == Sop.effective_revision_id).where(
        Sop.tenant_id == tenant_id, SopRevision.review_due <= horizon).order_by(SopRevision.review_due)).all()
    overdue = db.scalars(select(TrainingAssignment).where(
        TrainingAssignment.tenant_id == tenant_id, TrainingAssignment.status == "assigned",
        TrainingAssignment.due_date < today).order_by(TrainingAssignment.due_date))
    return {
        "reviews_due": [{"sop_id": s.id, "doc_number": s.doc_number, "review_due": r.review_due,
                         "overdue": r.review_due < today} for s, r in sops],
        "overdue_training": [{"assignment_id": a.id, "user_id": a.user_id, "revision_id": a.revision_id,
                              "due_date": a.due_date} for a in overdue],
    }
