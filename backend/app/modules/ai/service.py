"""Quality agent. It reaches data only through the same permission checks a user faces, as the tenant's
AI principal, and its only write path is an ai_draft row."""
import uuid
from datetime import datetime, time

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.core.security import Principal, principal_from_user
from app.modules.ai import llm
from app.modules.ai.models import AiDraft, AiRun
from app.modules.audit import service as audit
from app.modules.documents import search
from app.modules.identity.models import Membership, Tenant, User
from app.modules.quality.models import Deviation
from app.modules.records import service as records


def _ai_principal(db: Session, tenant_id: uuid.UUID) -> Principal:
    uid = db.scalars(
        select(User.id).join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id, User.kind == "ai", Membership.active.is_(True), User.active.is_(True))
    ).first()
    if not uid:
        raise HTTPException(409, "no AI principal is provisioned for this tenant")
    return principal_from_user(db, uid)


def select_provider(db: Session, tenant_id: uuid.UUID):
    """External inference only when the tenant opted in AND a key exists; otherwise nothing leaves."""
    tenant = db.get(Tenant, tenant_id)
    if tenant and tenant.ai_external_inference:
        ext = llm.external_provider_factory()
        if ext:
            return ext
    return llm.LocalProvider()


def tokens_used_today(db: Session, tenant_id: uuid.UUID) -> int:
    start = datetime.combine(utcnow().date(), time.min)
    return db.scalar(select(func.coalesce(func.sum(AiRun.tokens), 0)).where(
        AiRun.tenant_id == tenant_id, AiRun.created_at >= start)) or 0


def _dev_source(db: Session, ai: Principal, d: Deviation) -> dict:
    if not ai.can("deviation.read"):
        raise HTTPException(403, "AI principal lacks deviation.read")
    r = records.get_record(db, ai, d.record_id, "deviation")
    c = records.current_version(db, r).content
    return {"source_id": f"dev:{d.record_id}", "state": r.state, "title": c.get("title"),
            "description": c.get("description"), "equipment_id": c.get("equipment_id"),
            "batch_id": c.get("batch_id"), "area": c.get("area")}


def _related(db: Session, ai: Principal, d: Deviation) -> list[dict]:
    if not d.equipment_id:
        return []
    rows = db.scalars(select(Deviation).where(
        Deviation.tenant_id == ai.tenant_id, Deviation.equipment_id == d.equipment_id,
        Deviation.record_id != d.record_id).order_by(Deviation.opened_at.desc()).limit(8))
    return [_dev_source(db, ai, x) for x in rows]


def run_quality_draft(db: Session, requester: Principal, deviation_id: uuid.UUID, investigation_id: uuid.UUID) -> AiDraft:
    ai = _ai_principal(db, requester.tenant_id)
    dev = db.scalars(select(Deviation).where(
        Deviation.record_id == deviation_id, Deviation.tenant_id == requester.tenant_id)).first()
    if not dev:
        raise HTTPException(404, "not found")
    records.get_record(db, requester, investigation_id, "investigation")
    if tokens_used_today(db, requester.tenant_id) >= settings.ai_daily_token_budget:
        raise HTTPException(429, "this tenant's daily AI budget is used up")

    deviation = _dev_source(db, ai, dev)
    related = _related(db, ai, dev)
    query = " ".join(filter(None, [deviation["title"], deviation["description"], deviation["equipment_id"]]))
    passages = search.search(db, ai, query, k=5)  # as the AI principal: needs sop.read
    context = {"deviation": deviation, "related": related, "sop_passages": passages}
    allowed = llm.allowed_source_ids(context)

    provider = select_provider(db, requester.tenant_id)
    try:
        result = provider.draft("five_whys_fishbone", context)
    except llm.AIProviderError as exc:
        raise HTTPException(502, f"AI draft unavailable: {exc}") from exc
    output = llm.validate_draft(result.output, allowed)

    tokens = result.input_tokens + result.output_tokens
    cost = (result.input_tokens * settings.ai_input_usd_per_mtok + result.output_tokens * settings.ai_output_usd_per_mtok) / 1e6
    run = AiRun(
        tenant_id=requester.tenant_id, principal_id=ai.user_id, requested_by=requester.user_id, agent="quality",
        model_name=result.model, model_version=result.version, provider=provider.name, external=provider.external,
        prompt_version=llm.PROMPT_VERSION, inputs={"deviation_id": str(deviation_id), "query": query},
        source_record_ids=sorted(allowed), output=output, tokens=tokens, cost_usd=round(cost, 6), created_at=utcnow(),
    )
    db.add(run)
    db.flush()
    if not ai.can("ai.draft.create"):
        raise HTTPException(403, "AI principal lacks ai.draft.create")
    draft = AiDraft(
        tenant_id=requester.tenant_id, ai_run_id=run.id, target_record_id=investigation_id,
        content={**output, "sources": sorted(allowed), "label": "AI-GENERATED DRAFT - not reviewed",
                 "provider": provider.name},
    )
    db.add(draft)
    db.flush()
    audit.record_event(
        db, tenant_id=requester.tenant_id, actor_id=ai.user_id, actor_kind="ai", action="ai_draft.create",
        entity_type="ai_draft", entity_id=draft.id,
        new={"run": str(run.id), "provider": provider.name, "external": provider.external, "model": result.model,
             "tokens": tokens, "sources": sorted(allowed), **output["validation"]},
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
        "five_whys": draft.content["five_whys"], "fishbone": draft.content["fishbone"],
        "ai_provenance": {"ai_draft_id": str(draft.id), "ai_run_id": str(draft.ai_run_id), "adopted_by": str(p.user_id),
                          "sources": draft.content["sources"], "unreviewed_items": draft.content["validation"]["unsupported_items"]},
    })
    records.edit_draft(db, p, r, content, reason)
    draft.status, draft.adopted_by = "adopted", p.user_id
    audit.record_event(
        db, tenant_id=p.tenant_id, actor_id=p.user_id, actor_kind=p.kind, action="ai_draft.adopt",
        entity_type="ai_draft", entity_id=draft.id, new={"target": str(r.id)}, reason=reason,
    )
    return draft
