import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Principal, require
from app.modules.ai import service

router = APIRouter(tags=["ai"])


class DraftRequest(BaseModel):
    investigation_id: uuid.UUID


class AdoptRequest(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/deviations/{deviation_id}/ai-draft", status_code=201)
def request_draft(deviation_id: uuid.UUID, body: DraftRequest, p: Principal = Depends(require("deviation.investigate")),
                  db: Session = Depends(get_db)):
    d = service.run_quality_draft(db, p, deviation_id, body.investigation_id)
    return {"id": d.id, "status": d.status, "content": d.content}


@router.post("/ai-drafts/{draft_id}/adopt")
def adopt_draft(draft_id: uuid.UUID, body: AdoptRequest, p: Principal = Depends(require("ai.adopt")),
                db: Session = Depends(get_db)):
    d = service.adopt(db, p, draft_id, body.reason)
    return {"id": d.id, "status": d.status}
