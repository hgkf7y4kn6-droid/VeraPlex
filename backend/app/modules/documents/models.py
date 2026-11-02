import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, Text, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, new_id


class Sop(Base):
    """Identity of a controlled SOP; each revision is its own controlled record."""
    __tablename__ = "sop"
    __table_args__ = (UniqueConstraint("tenant_id", "doc_number"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    doc_number: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    review_interval_months: Mapped[int] = mapped_column(Integer, default=24)
    effective_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class SopRevision(Base):
    __tablename__ = "sop_revision"
    __table_args__ = (UniqueConstraint("sop_id", "revision_no"),)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record.id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    sop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sop.id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_due: Mapped[date | None] = mapped_column(Date, nullable=True)


class TrainingAssignment(Base):
    __tablename__ = "training_assignment"
    __table_args__ = (UniqueConstraint("revision_id", "user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sop_revision.record_id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(15), default="assigned")  # assigned | acknowledged | superseded
    assigned_at: Mapped[datetime] = mapped_column(DateTime)


class Acknowledgment(Base):
    """Append-only read-and-understood record, bound to the exact content hash and a re-auth event."""
    __tablename__ = "acknowledgment"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_assignment.id"), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    user_name: Mapped[str] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime)
    reauth_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reauth_event.id"))


class SopChunk(Base):
    """Searchable passage of an effective SOP revision. Embeddings are stored as JSON and scored in
    process (fine at pilot scale); pgvector is the upgrade path once corpus size justifies it."""
    __tablename__ = "sop_chunk"
    __table_args__ = (UniqueConstraint("revision_id", "chunk_no", "embedder"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sop_revision.record_id"), index=True)
    chunk_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(JSON)
    embedder: Mapped[str] = mapped_column(String(80))
