from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Signature(Base):
    __tablename__ = "signature"
    __table_args__ = (UniqueConstraint("record_version_id", "signer_id", "meaning"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    record_version_id: Mapped[str] = mapped_column(ForeignKey("record_version.id"))
    signer_id: Mapped[str] = mapped_column(String(64))
    signer_name: Mapped[str] = mapped_column(String(200))
    meaning: Mapped[str] = mapped_column(String(16))  # authored|reviewed|approved|verified
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    reauth_event_id: Mapped[str] = mapped_column(String(64))
