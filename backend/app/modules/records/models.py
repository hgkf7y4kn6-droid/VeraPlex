from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Record(Base):
    __tablename__ = "record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))  # draft|in_review|approved|retired
    current_version: Mapped[int] = mapped_column(Integer)


class RecordVersion(Base):
    __tablename__ = "record_version"
    __table_args__ = (UniqueConstraint("record_id", "version_no"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("record.id"))
    version_no: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
