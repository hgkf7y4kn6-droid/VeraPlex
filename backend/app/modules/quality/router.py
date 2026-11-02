import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Principal, require
from app.modules.quality import service
from app.modules.quality.models import Capa, Deviation, Investigation
from app.modules.records import service as records

router = APIRouter(tags=["quality"])


class DeviationIn(BaseModel):
    title: str = Field(min_length=3)
    description: str
    batch_id: str | None = None
    equipment_id: str | None = None
    area: str | None = None


class TriageIn(BaseModel):
    severity: int
    occurrence: int
    detectability: int
    owner_id: uuid.UUID
    due_date: date
    reason: str = "triage"


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


class InvestigationIn(BaseModel):
    five_whys: list[dict] = []
    root_cause: str | None = None
    reason: str = Field(min_length=3, default="investigation update")


class SignIn(BaseModel):
    reauth_token: str
    meaning: str = "approved"


class CapaIn(BaseModel):
    title: str = Field(min_length=3)
    root_cause: str
    actions: list[dict]


def _signed(db, r):
    v = records.current_version(db, r)
    return [records.manifestation(s) for s in records.signatures_for(db, v)]


def _dev_view(db, p, d: Deviation):
    r = records.get_record(db, p, d.record_id, "deviation")
    return {"id": d.record_id, "state": r.state, "content": records.current_version(db, r).content,
            "recurring": d.recurring, "risk_score": d.risk_score, "classification": d.classification,
            "equipment_id": d.equipment_id}


@router.post("/deviations", status_code=201)
def create_deviation(body: DeviationIn, p: Principal = Depends(require("deviation.create")), db: Session = Depends(get_db)):
    d = service.raise_deviation(db, p, body.model_dump(mode="json"))
    return _dev_view(db, p, d)


@router.get("/deviations")
def list_deviations(p: Principal = Depends(require("deviation.read")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Deviation).where(Deviation.tenant_id == p.tenant_id).order_by(Deviation.opened_at.desc()))
    return [_dev_view(db, p, d) for d in rows]


@router.get("/deviations/{rid}")
def read_deviation(rid: uuid.UUID, p: Principal = Depends(require("deviation.read")), db: Session = Depends(get_db)):
    return _dev_view(db, p, service.get_deviation(db, p, rid))


@router.post("/deviations/{rid}/triage")
def triage(rid: uuid.UUID, body: TriageIn, p: Principal = Depends(require("deviation.triage")), db: Session = Depends(get_db)):
    d = service.get_deviation(db, p, rid)
    service.triage(db, p, d, body.severity, body.occurrence, body.detectability, body.owner_id, body.due_date, body.reason)
    return _dev_view(db, p, d)


@router.post("/deviations/{rid}/investigation", status_code=201)
def start_investigation(rid: uuid.UUID, body: ReasonIn, p: Principal = Depends(require("deviation.investigate")),
                        db: Session = Depends(get_db)):
    inv = service.start_investigation(db, p, service.get_deviation(db, p, rid), body.reason)
    return {"investigation_id": inv.record_id}


@router.put("/investigations/{rid}")
def edit_investigation(rid: uuid.UUID, body: InvestigationIn, p: Principal = Depends(require("deviation.investigate")),
                       db: Session = Depends(get_db)):
    r = records.get_record(db, p, rid, "investigation")
    existing = records.current_version(db, r).content
    content = {**existing, "five_whys": body.five_whys, "root_cause": body.root_cause}
    return records.edit_draft(db, p, r, content, body.reason).content


@router.post("/investigations/{rid}/complete")
def complete_investigation(rid: uuid.UUID, body: SignIn, p: Principal = Depends(require("deviation.investigate")),
                           db: Session = Depends(get_db)):
    r = records.get_record(db, p, rid, "investigation")
    records.sign(db, p, r, "authored", body.reauth_token)
    from app.modules.quality import rules
    records.transition(db, p, r, "complete", rules.INVESTIGATION, "investigation complete")
    return {"state": r.state, "signatures": _signed(db, r)}


@router.post("/deviations/{rid}/capas", status_code=201)
def propose_capa(rid: uuid.UUID, body: CapaIn, p: Principal = Depends(require("capa.create")), db: Session = Depends(get_db)):
    capa = service.propose_capa(db, p, service.get_deviation(db, p, rid), body.model_dump())
    return {"capa_id": capa.record_id}


def _capa(db, p, rid) -> Capa:
    c = db.scalars(select(Capa).where(Capa.record_id == rid, Capa.tenant_id == p.tenant_id)).first()
    if not c:
        raise HTTPException(404, "not found")
    return c


@router.get("/capas/{rid}")
def read_capa(rid: uuid.UUID, p: Principal = Depends(require("capa.read")), db: Session = Depends(get_db)):
    c = _capa(db, p, rid)
    r = records.get_record(db, p, rid, "capa")
    return {"id": rid, "state": r.state, "content": records.current_version(db, r).content,
            "signatures": _signed(db, r), "effectiveness_due": c.effectiveness_due}


@router.post("/capas/{rid}/submit")
def submit_capa(rid: uuid.UUID, p: Principal = Depends(require("capa.submit")), db: Session = Depends(get_db)):
    service.capa_transition(db, p, _capa(db, p, rid), "pending_approval", "submitted for approval")
    return {"state": "pending_approval"}


@router.post("/capas/{rid}/sign")
def sign_capa(rid: uuid.UUID, body: SignIn, p: Principal = Depends(require("capa.approve")), db: Session = Depends(get_db)):
    _capa(db, p, rid)
    r = records.get_record(db, p, rid, "capa")
    if r.state != "pending_approval":
        raise HTTPException(409, "CAPA is not pending approval")
    records.sign(db, p, r, body.meaning, body.reauth_token)
    return {"signatures": _signed(db, r)}


@router.post("/capas/{rid}/transition/{to}")
def capa_transition(rid: uuid.UUID, to: str, body: ReasonIn, db: Session = Depends(get_db),
                    p: Principal = Depends(require("capa.approve"))):
    perm = {"approved": "capa.approve", "rejected": "capa.approve", "in_progress": "capa.action",
            "effectiveness_check": "capa.action", "closed": "capa.close"}.get(to)
    if not perm or not p.can(perm):
        raise HTTPException(403, "not permitted for this transition")
    service.capa_transition(db, p, _capa(db, p, rid), to, body.reason)
    return {"state": to}


class ChangeControlIn(BaseModel):
    sop_id: uuid.UUID
    rationale: str = Field(min_length=3)
    new_body: str


@router.post("/capas/{rid}/change-controls", status_code=201)
def open_change_control(rid: uuid.UUID, body: ChangeControlIn, p: Principal = Depends(require("change_control.open")),
                        db: Session = Depends(get_db)):
    from app.modules.quality import change_control
    cc = change_control.open_change_control(db, p, _capa(db, p, rid), body.sop_id, body.rationale, body.new_body)
    return {"change_control_id": cc.record_id, "sop_revision_id": cc.new_revision_id}


@router.post("/change-controls/{rid}/close")
def close_change_control(rid: uuid.UUID, body: ReasonIn, p: Principal = Depends(require("change_control.close")),
                         db: Session = Depends(get_db)):
    from app.modules.quality import change_control
    change_control.close(db, p, change_control.get(db, p, rid), body.reason)
    return {"state": "closed"}


@router.get("/change-controls/{rid}")
def read_change_control(rid: uuid.UUID, p: Principal = Depends(require("capa.read")), db: Session = Depends(get_db)):
    from app.modules.quality import change_control
    cc = change_control.get(db, p, rid)
    r = records.get_record(db, p, rid, "change_control")
    return {"id": rid, "state": r.state, "capa_id": cc.capa_id, "sop_id": cc.sop_id, "new_revision_id": cc.new_revision_id}
