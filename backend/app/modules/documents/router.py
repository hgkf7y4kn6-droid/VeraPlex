import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.database import get_db
from app.core.security import Principal, require
from app.modules.documents import service
from app.modules.documents.models import Sop, SopRevision, TrainingAssignment
from app.modules.records import service as records

router = APIRouter(tags=["documents"])


class SopIn(BaseModel):
    doc_number: str = Field(min_length=2)
    title: str = Field(min_length=3)
    body: str
    review_interval_months: int = Field(default=24, ge=1, le=60)
    training_roles: list[str] | None = None


class RevisionIn(BaseModel):
    body: str
    change_summary: str = Field(min_length=3)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


class SignIn(BaseModel):
    meaning: str
    reauth_token: str


class AckIn(BaseModel):
    reauth_token: str


def _rev_view(db, p, rev: SopRevision):
    r = records.get_record(db, p, rev.record_id, "sop_revision")
    v = records.current_version(db, r)
    return {"id": rev.record_id, "sop_id": rev.sop_id, "revision_no": rev.revision_no, "state": r.state,
            "content": v.content, "effective_date": rev.effective_date, "review_due": rev.review_due,
            "signatures": [records.manifestation(s) for s in records.signatures_for(db, v)]}


@router.post("/sops", status_code=201)
def create_sop(body: SopIn, p: Principal = Depends(require("sop.author")), db: Session = Depends(get_db)):
    sop, rev = service.create_sop(db, p, body.doc_number, body.title, body.body, body.review_interval_months, body.training_roles)
    return {"sop_id": sop.id, "revision_id": rev.record_id}


@router.get("/sops")
def list_sops(p: Principal = Depends(require("sop.read")), db: Session = Depends(get_db)):
    return [{"id": s.id, "doc_number": s.doc_number, "title": s.title, "effective_revision_id": s.effective_revision_id}
            for s in db.scalars(select(Sop).where(Sop.tenant_id == p.tenant_id).order_by(Sop.doc_number))]


@router.get("/sops/search")
def search_sops(q: str, k: int = 5, p: Principal = Depends(require("sop.read")), db: Session = Depends(get_db)):
    from app.modules.documents import search
    return search.search(db, p, q[:500], max(1, min(k, 20)))


@router.post("/sops/reindex")
def reindex(p: Principal = Depends(require("sop.admin")), db: Session = Depends(get_db)):
    from app.modules.documents import search
    return {"chunks": search.reindex_all(db, p)}


@router.get("/sops/reminders")
def reminders(p: Principal = Depends(require("sop.admin")), db: Session = Depends(get_db)):
    return service.reminders(db, p.tenant_id, utcnow().date())


@router.get("/sops/{sop_id}/revisions")
def revisions(sop_id: uuid.UUID, p: Principal = Depends(require("sop.read")), db: Session = Depends(get_db)):
    service.get_sop(db, p, sop_id)
    return [_rev_view(db, p, r) for r in db.scalars(select(SopRevision).where(
        SopRevision.sop_id == sop_id, SopRevision.tenant_id == p.tenant_id).order_by(SopRevision.revision_no))]


@router.post("/sops/{sop_id}/revisions", status_code=201)
def open_revision(sop_id: uuid.UUID, body: RevisionIn, p: Principal = Depends(require("sop.author")), db: Session = Depends(get_db)):
    rev = service.open_revision(db, p, service.get_sop(db, p, sop_id), body.body, body.change_summary)
    return _rev_view(db, p, rev)


@router.get("/sop-revisions/{rid}")
def read_revision(rid: uuid.UUID, p: Principal = Depends(require("sop.read")), db: Session = Depends(get_db)):
    return _rev_view(db, p, service.get_revision(db, p, rid))


@router.put("/sop-revisions/{rid}")
def edit_revision(rid: uuid.UUID, body: RevisionIn, p: Principal = Depends(require("sop.author")), db: Session = Depends(get_db)):
    rev = service.get_revision(db, p, rid)
    r = records.get_record(db, p, rid, "sop_revision")
    records.edit_draft(db, p, r, {**records.current_version(db, r).content, "body": body.body,
                                  "change_summary": body.change_summary}, body.change_summary)
    return _rev_view(db, p, rev)


@router.post("/sop-revisions/{rid}/submit")
def submit(rid: uuid.UUID, body: ReasonIn, p: Principal = Depends(require("sop.author")), db: Session = Depends(get_db)):
    service.submit_for_review(db, p, service.get_revision(db, p, rid), body.reason)
    return {"state": "in_review"}


@router.post("/sop-revisions/{rid}/sign")
def sign(rid: uuid.UUID, body: SignIn, p: Principal = Depends(require("sop.review")), db: Session = Depends(get_db)):
    from fastapi import HTTPException
    rev = service.get_revision(db, p, rid)
    if body.meaning not in ("reviewed", "approved") or (body.meaning == "approved" and not p.can("sop.approve")):
        raise HTTPException(403, "not permitted to sign with this meaning")
    r = records.get_record(db, p, rid, "sop_revision")
    if r.state != "in_review":
        raise HTTPException(409, "revision is not in review")
    records.sign(db, p, r, body.meaning, body.reauth_token)
    return _rev_view(db, p, rev)


@router.post("/sop-revisions/{rid}/approve")
def approve(rid: uuid.UUID, body: ReasonIn, p: Principal = Depends(require("sop.approve")), db: Session = Depends(get_db)):
    service.approve(db, p, service.get_revision(db, p, rid), body.reason)
    return {"state": "approved"}


@router.post("/sop-revisions/{rid}/make-effective")
def make_effective(rid: uuid.UUID, p: Principal = Depends(require("sop.approve")), db: Session = Depends(get_db)):
    out = service.make_effective(db, p, service.get_revision(db, p, rid))
    return {"state": "effective", "training_assigned": len(out)}


@router.get("/me/training")
def my_training(p: Principal = Depends(require("training.ack")), db: Session = Depends(get_db)):
    return [{"id": a.id, "revision_id": a.revision_id, "due_date": a.due_date, "status": a.status}
            for a in db.scalars(select(TrainingAssignment).where(
                TrainingAssignment.user_id == p.user_id, TrainingAssignment.tenant_id == p.tenant_id))]


@router.post("/training/{aid}/acknowledge")
def acknowledge(aid: uuid.UUID, body: AckIn, p: Principal = Depends(require("training.ack")), db: Session = Depends(get_db)):
    ack = service.acknowledge(db, p, aid, body.reauth_token)
    return {"acknowledged_at_utc": ack.acknowledged_at.isoformat() + "Z", "user": ack.user_name, "content_hash": ack.content_hash}
