from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Principal, require
from app.modules.audit import service
from app.modules.audit.models import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events")
def events(limit: int = 100, p: Principal = Depends(require("audit.read")), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == p.tenant_id)
                      .order_by(AuditEvent.seq.desc()).limit(min(limit, 500)))
    return [{"seq": e.seq, "at": e.occurred_at, "actor": e.actor_id, "actor_kind": e.actor_kind, "action": e.action,
             "entity": e.entity_type, "entity_id": e.entity_id, "reason": e.reason, "hash": e.hash} for e in rows]


@router.get("/verify")
def verify(p: Principal = Depends(require("audit.verify")), db: Session = Depends(get_db)):
    return service.verify_chain(db, p.tenant_id)
