import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, new_id


class AiRun(Base):
    __tablename__ = "ai_run"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    principal_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    agent: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40), default="local", server_default="local")
    external: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    prompt_version: Mapped[str] = mapped_column(String(40))
    inputs: Mapped[dict] = mapped_column(JSON)
    source_record_ids: Mapped[list] = mapped_column(JSON)
    output: Mapped[dict] = mapped_column(JSON)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AiDraft(Base):
    __tablename__ = "ai_draft"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    ai_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_run.id"))
    target_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record.id"), index=True)
    content: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | adopted
    adopted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
