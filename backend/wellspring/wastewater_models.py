"""Organization-scoped wastewater monitoring records; independent of personal cases."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, now
from .types import ExactDecimal, UTCDateTime


class WastewaterSite(Base):
    __tablename__ = "wastewater_sites"
    __table_args__ = (UniqueConstraint("org_id", "code", name="uq_wastewater_site_org_code"),
                      Index("ix_wastewater_site_org_created", "org_id", "created_at", "id"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    district: Mapped[str] = mapped_column(String(200))
    plant_name: Mapped[str] = mapped_column(String(200), default="")
    catchment: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    state_note: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class WastewaterSample(Base):
    __tablename__ = "wastewater_samples"
    __table_args__ = (UniqueConstraint("org_id", "code", name="uq_wastewater_sample_org_code"),
                      Index("ix_wastewater_sample_org_site_time", "org_id", "site_id", "sampled_at", "id"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    site_id: Mapped[str] = mapped_column(ForeignKey("wastewater_sites.id"))
    code: Mapped[str] = mapped_column(String(80))
    sampled_at: Mapped[datetime] = mapped_column(UTCDateTime())
    sampling_method: Mapped[str] = mapped_column(String(30))
    collector: Mapped[str] = mapped_column(String(100))
    flow_m3_day: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    quality: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class WastewaterResult(Base):
    __tablename__ = "wastewater_results"
    __table_args__ = (UniqueConstraint("sample_id", "analyte", "laboratory", "report_number", name="uq_wastewater_result_report"),
                      Index("ix_wastewater_result_org_state_created", "org_id", "state", "created_at", "id"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    sample_id: Mapped[str] = mapped_column(ForeignKey("wastewater_samples.id"))
    analyte: Mapped[str] = mapped_column(String(120))
    detection: Mapped[str] = mapped_column(String(30))
    concentration: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    quantification_limit: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    laboratory: Mapped[str] = mapped_column(String(200))
    analysis_method: Mapped[str] = mapped_column(String(200))
    report_number: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(30), default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class WastewaterResultEvent(Base):
    __tablename__ = "wastewater_result_events"
    __table_args__ = (Index("ix_wastewater_event_result_created", "result_id", "created_at", "id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    result_id: Mapped[str] = mapped_column(ForeignKey("wastewater_results.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
