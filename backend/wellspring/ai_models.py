"""Model service configuration and owner-scoped drafts, separate from business facts."""
from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import now, uid
from .types import UTCDateTime


class AiService(Base):
    __tablename__ = "ai_services"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="primary")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    base_url: Mapped[str] = mapped_column(String(1000), default="")
    model: Mapped[str] = mapped_column(String(200), default="")
    api_key_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    token_parameter: Mapped[str] = mapped_column(String(30), default="max_tokens")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    check_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    check_message: Mapped[str] = mapped_column(String(300), default="")


class AiRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        Index("ix_ai_run_owner_created", "org_id", "actor_id", "created_at", "id"),
        Index("uq_ai_run_active_actor", "actor_id", unique=True,
              sqlite_where=text("status IN ('QUEUED','RUNNING')"),
              postgresql_where=text("status IN ('QUEUED','RUNNING')")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    model: Mapped[str] = mapped_column(String(200))
    service_version: Mapped[int] = mapped_column(Integer)
    input_sha256: Mapped[str] = mapped_column(String(64))
    input_chars: Mapped[int] = mapped_column(Integer)
    output_text: Mapped[str] = mapped_column(Text, default="")
    error_code: Mapped[str] = mapped_column(String(60), default="")
    error_message: Mapped[str] = mapped_column(String(300), default="")
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
