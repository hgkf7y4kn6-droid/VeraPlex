import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


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
