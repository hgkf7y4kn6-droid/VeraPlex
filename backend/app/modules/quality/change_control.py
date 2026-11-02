"""CAPA -> SOP change control. Opening one drafts a new SOP revision; when that revision becomes
effective the documents module fires a hook and training is assigned there."""
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.modules.documents import service as documents
from app.modules.documents.models import SopRevision
from app.modules.quality import rules
from app.modules.quality.models import Capa, ChangeControl
from app.modules.records import service as records


def open_change_control(db: Session, p: Principal, capa: Capa, sop_id: uuid.UUID, rationale: str, new_body: str) -> ChangeControl:
    capa_rec = records.get_record(db, p, capa.record_id, "capa")
    if capa_rec.state not in ("approved", "in_progress", "effectiveness_check"):
        raise HTTPException(409, "change control can only be opened from an approved CAPA")
    sop = documents.get_sop(db, p, sop_id)
    rev = documents.open_revision(db, p, sop, new_body, f"CAPA {capa.record_id}: {rationale}")
    rec = records.create(db, p, "change_control", "open",
                         {"capa_id": str(capa.record_id), "sop_id": str(sop.id), "rationale": rationale,
                          "new_revision_id": str(rev.record_id)}, "change control opened from CAPA")
    cc = ChangeControl(record_id=rec.id, tenant_id=p.tenant_id, capa_id=capa.record_id, sop_id=sop.id,
                       new_revision_id=rev.record_id)
    db.add(cc)
    db.flush()
    return cc


def get(db: Session, p: Principal, rid: uuid.UUID) -> ChangeControl:
    cc = db.scalars(select(ChangeControl).where(ChangeControl.record_id == rid, ChangeControl.tenant_id == p.tenant_id)).first()
    if not cc:
        raise HTTPException(404, "not found")
    return cc


def close(db: Session, p: Principal, cc: ChangeControl, reason: str):
    records.transition(db, p, records.get_record(db, p, cc.record_id, "change_control"), "closed", rules.CHANGE_CONTROL, reason)


@documents.on_revision_effective
def _mark_implemented(db: Session, p: Principal, rev: SopRevision) -> None:
    for cc in db.scalars(select(ChangeControl).where(
        ChangeControl.new_revision_id == rev.record_id, ChangeControl.tenant_id == p.tenant_id)):
        r = records.get_record(db, p, cc.record_id, "change_control")
        if r.state == "open":
            records.transition(db, p, r, "implemented", rules.CHANGE_CONTROL, "SOP revision became effective")
