"""Quality agent. It reaches data only through the same permission checks a user faces,
as the tenant's AI principal, and its only write path is an ai_draft row."""
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import providers
from app.core.clock import utcnow
from app.core.security import Principal, principal_from_user
from app.modules.ai.models import AiDraft, AiRun
from app.modules.audit import service as audit
from app.modules.identity.models import Membership, User
from app.modules.quality.models import Deviation
from app.modules.records import service as records

PROMPT_VERSION = "quality-draft-v0"


def _ai_principal(db: Session, tenant_id: uuid.UUID) -> Principal:
    uid = db.scalars(
        select(User.id).join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id, User.kind == "ai", Membership.active.is_(True), User.active.is_(True))
    ).first()
    if not uid:
        raise HTTPException(409, "no AI principal is provisioned for this tenant")
    return principal_from_user(db, uid)


def _tool_read_deviation(db: Session, ai: Principal, record_id: uuid.UUID) -> dict:
    if not ai.can("deviation.read"):
        raise HTTPException(403, "AI principal lacks deviation.read")
    r = records.get_record(db, ai, record_id, "deviation")
    return {"id": str(r.id), **records.current_version(db, r).content}


def _tool_related(db: Session, ai: Principal, d: Deviation) -> list[dict]:
    if not ai.can("deviation.read"):
        raise HTTPException(403, "AI principal lacks deviation.read")
    if not d.equipment_id:
        return []
    rows = db.scalars(select(Deviation).where(
        Deviation.tenant_id == ai.tenant_id, Deviation.equipment_id == d.equipment_id,
        Deviation.record_id != d.record_id).order_by(Deviation.opened_at.desc()).limit(10))
    return [_tool_read_deviation(db, ai, x.record_id) for x in rows]


def run_quality_draft(db: Session, requester: Principal, deviation_id: uuid.UUID, investigation_id: uuid.UUID) -> AiDraft:
    ai = _ai_principal(db, requester.tenant_id)
    dev = db.scalars(select(Deviation).where(
        Deviation.record_id == deviation_id, Deviation.tenant_id == requester.tenant_id)).first()
    if not dev:
        raise HTTPException(404, "not found")
    records.get_record(db, requester, investigation_id, "investigation")
    deviation = _tool_read_deviation(db, ai, deviation_id)
    related = _tool_related(db, ai, dev)
    mp = providers.model_provider
    out = mp.draft("five_whys_fishbone", {"deviation": deviation, "related": related})
    sources = [str(deviation_id)] + [x["id"] for x in related]
    run = AiRun(
        tenant_id=requester.tenant_id, principal_id=ai.user_id, requested_by=requester.user_id,
        agent="quality", model_name=mp.name, model_version=mp.version, prompt_version=PROMPT_VERSION,
        inputs={"deviation_id": str(deviation_id)}, source_record_ids=sources, output=out, created_at=utcnow(),
    )
    db.add(run)
    db.flush()
    if not ai.can("ai.draft.create"):
        raise HTTPException(403, "AI principal lacks ai.draft.create")
    draft = AiDraft(
        tenant_id=requester.tenant_id, ai_run_id=run.id, target_record_id=investigation_id,
        content={**out, "sources": sources, "label": "AI-GENERATED DRAFT - not reviewed"},
    )
    db.add(draft)
    db.flush()
    audit.record_event(
        db, tenant_id=requester.tenant_id, actor_id=ai.user_id, actor_kind="ai", action="ai_draft.create",
        entity_type="ai_draft", entity_id=draft.id, new={"run": str(run.id), "sources": sources},
        reason=f"requested by {requester.user_id}",
    )
    return draft


def adopt(db: Session, p: Principal, draft_id: uuid.UUID, reason: str) -> AiDraft:
    draft = db.scalars(select(AiDraft).where(AiDraft.id == draft_id, AiDraft.tenant_id == p.tenant_id)).first()
    if not draft:
        raise HTTPException(404, "not found")
    if draft.status != "draft":
        raise HTTPException(409, "draft already adopted")
    r = records.get_record(db, p, draft.target_record_id, "investigation")
    content = {**records.current_version(db, r).content}
    content.update({
        "five_whys": draft.content["five_whys"], "fishbone_categories": draft.content["fishbone_categories"],
        "ai_provenance": {"ai_draft_id": str(draft.id), "ai_run_id": str(draft.ai_run_id), "adopted_by": str(p.user_id)},
    })
    records.edit_draft(db, p, r, content, reason)
    draft.status, draft.adopted_by = "adopted", p.user_id
    audit.record_event(
        db, tenant_id=p.tenant_id, actor_id=p.user_id, actor_kind=p.kind, action="ai_draft.adopt",
        entity_type="ai_draft", entity_id=draft.id, new={"target": str(r.id)}, reason=reason,
    )
    return draft
