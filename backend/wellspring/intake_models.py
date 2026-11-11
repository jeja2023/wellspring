"""Explicit, traceable links from retained intake records to case drafts."""
from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, now
from .types import UTCDateTime


class IntakeCaseLink(Base):
    __tablename__ = "intake_case_links"
    __table_args__ = (
        Index("uq_intake_case_active", "intake_id", unique=True,
              sqlite_where=text("status = 'ACTIVE'"), postgresql_where=text("status = 'ACTIVE'")),
        Index("ix_intake_case_case_created", "org_id", "case_id", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    intake_id: Mapped[str] = mapped_column(ForeignKey("case_information.id"))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    source_version: Mapped[int] = mapped_column(Integer)
    source_number: Mapped[str] = mapped_column(String(80))
    source_snapshot: Mapped[str] = mapped_column(Text)
    created_case: Mapped[bool] = mapped_column(Boolean)
    basis: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    revoked_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
