import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, new_id


class Record(Base):
    __tablename__ = "record"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    state: Mapped[str] = mapped_column(String(40))
    current_version_no: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class RecordVersion(Base):
    __tablename__ = "record_version"
    __table_args__ = (UniqueConstraint("record_id", "version_no"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)


class RecordStateTransition(Base):
    __tablename__ = "record_state_transition"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record.id"), index=True)
    from_state: Mapped[str] = mapped_column(String(40))
    to_state: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime)


class ReauthEvent(Base):
    """One row per accepted re-authentication; a token (jti) can sign exactly once."""
    __tablename__ = "reauth_event"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    jti: Mapped[str] = mapped_column(String(128), unique=True)
    at: Mapped[datetime] = mapped_column(DateTime)


class Signature(Base):
    __tablename__ = "signature"
    __table_args__ = (UniqueConstraint("record_version_id", "signer_id", "meaning"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    record_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record_version.id"), index=True)
    signer_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    signer_name: Mapped[str] = mapped_column(String(200))
    signer_role: Mapped[str] = mapped_column(String(40))
    meaning: Mapped[str] = mapped_column(String(20))
    signed_at: Mapped[datetime] = mapped_column(DateTime)
    content_hash: Mapped[str] = mapped_column(String(64))
    reauth_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reauth_event.id"))
