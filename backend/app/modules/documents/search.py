"""SOP search over *effective* revisions only (superseded or draft text is never returned)."""
import math
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import providers
from app.core.security import Principal
from app.modules.documents.models import Sop, SopChunk, SopRevision

MAX_CHUNK = 900


def chunk_text(body: str, limit: int = MAX_CHUNK) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    pieces: list[str] = []
    for p in paras:
        while len(p) > limit:  # split long paragraphs on sentence boundaries where possible
            cut = max(p.rfind(". ", 0, limit), p.rfind("\n", 0, limit))
            cut = cut + 1 if cut > limit // 3 else limit
            pieces.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            pieces.append(p)
    chunks: list[str] = []
    for piece in pieces:  # merge small neighbours so chunks carry context
        if chunks and len(chunks[-1]) + len(piece) + 2 <= limit:
            chunks[-1] += "\n\n" + piece
        else:
            chunks.append(piece)
    return chunks


def index_revision(db: Session, tenant_id: uuid.UUID, rev: SopRevision, sop: Sop, content: dict) -> int:
    emb = providers.embedder
    db.execute(delete(SopChunk).where(SopChunk.revision_id == rev.record_id, SopChunk.embedder == emb.name))
    chunks = chunk_text(content.get("body", ""))
    if not chunks:
        return 0
    vecs = emb.embed([f"{sop.title}\n{c}" for c in chunks])
    for i, (c, v) in enumerate(zip(chunks, vecs)):
        db.add(SopChunk(tenant_id=tenant_id, revision_id=rev.record_id, chunk_no=i, text=c, embedding=v, embedder=emb.name))
    db.flush()
    return len(chunks)


def reindex_all(db: Session, p: Principal) -> int:
    from app.modules.records import service as records
    n = 0
    for sop in db.scalars(select(Sop).where(Sop.tenant_id == p.tenant_id, Sop.effective_revision_id.is_not(None))):
        rev = db.get(SopRevision, sop.effective_revision_id)
        r = records.get_record(db, p, rev.record_id)
        n += index_revision(db, p.tenant_id, rev, sop, records.current_version(db, r).content)
    return n


def search(db: Session, p: Principal, query: str, k: int = 5, min_score: float = 0.08) -> list[dict]:
    if not p.can("sop.read"):
        raise HTTPException(403, "missing permission: sop.read")
    if not query.strip():
        return []
    emb = providers.embedder
    qv = emb.embed([query])[0]
    rows = db.execute(
        select(SopChunk, Sop, SopRevision)
        .join(Sop, Sop.effective_revision_id == SopChunk.revision_id)
        .join(SopRevision, SopRevision.record_id == SopChunk.revision_id)
        .where(SopChunk.tenant_id == p.tenant_id, Sop.tenant_id == p.tenant_id, SopChunk.embedder == emb.name)
    ).all()
    scored = []
    for ch, sop, rev in rows:
        score = sum(a * b for a, b in zip(qv, ch.embedding))
        if math.isfinite(score) and score >= min_score:
            scored.append((score, ch, sop, rev))
    scored.sort(key=lambda t: -t[0])
    return [{
        "source_id": f"sop:{rev.record_id}#{ch.chunk_no}", "sop_id": sop.id, "doc_number": sop.doc_number,
        "title": sop.title, "revision_no": rev.revision_no, "revision_id": rev.record_id,
        "chunk_no": ch.chunk_no, "score": round(score, 4), "text": ch.text,
    } for score, ch, sop, rev in scored[:k]]
