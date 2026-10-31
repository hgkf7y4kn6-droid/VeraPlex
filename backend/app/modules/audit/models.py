from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditEvent(Base):
    """Append-only, hash-chained per tenant. Never updated or deleted."""

    __tablename__ = "audit_event"
    __table_args__ = (UniqueConstraint("tenant_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_kind: Mapped[str] = mapped_column(String(8))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


def _immutable(*_):
    raise RuntimeError("audit_event is append-only")


event.listen(AuditEvent, "before_update", _immutable)
event.listen(AuditEvent, "before_delete", _immutable)
