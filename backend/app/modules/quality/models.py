import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, new_id


class Deviation(Base):
    """Quality-owned index over a generic record; queryable fields for triage and recurrence."""
    __tablename__ = "deviation"
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record.id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    equipment_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    batch_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Investigation(Base):
    __tablename__ = "investigation"
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record.id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    deviation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deviation.record_id"), index=True)


class Capa(Base):
    __tablename__ = "capa"
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record.id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    deviation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deviation.record_id"), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    effectiveness_due: Mapped[date | None] = mapped_column(Date, nullable=True)


class ChangeControl(Base):
    __tablename__ = "change_control"
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record.id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    capa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("capa.record_id"), index=True)
    sop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sop.id"), index=True)
    new_revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sop_revision.record_id"), index=True)


class IdempotencyKey(Base):
    """Makes offline-queue retries safe: the same key from the same user never creates a second record."""
    __tablename__ = "idempotency_key"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "key"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
