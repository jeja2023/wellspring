"""Places, inspections and incident records; no personal tracking or biometric data."""
from datetime import date, datetime
from sqlalchemy import Boolean, CheckConstraint, Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, now
from .types import UTCDateTime


class Place(Base):
    __tablename__ = 'places'
    __table_args__ = (UniqueConstraint('org_id', 'code', name='uq_place_org_code'), Index('ix_place_org_updated', 'org_id', 'updated_at', 'id'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    district: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(500))
    responsible: Mapped[str] = mapped_column(String(100))
    management_basis: Mapped[str] = mapped_column(Text)
    review_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class PlaceInspection(Base):
    __tablename__ = 'place_inspections'
    __table_args__ = (Index('ix_place_inspection_scope', 'org_id', 'place_id', 'created_at', 'id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    place_id: Mapped[str] = mapped_column(ForeignKey('places.id'))
    inspected_on: Mapped[date] = mapped_column(Date)
    findings: Mapped[str] = mapped_column(Text)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    result_note: Mapped[str] = mapped_column(Text, default='')
    completed_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class PlaceIncident(Base):
    __tablename__ = 'place_incidents'
    __table_args__ = (Index('ix_place_incident_scope', 'org_id', 'place_id', 'created_at', 'id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    place_id: Mapped[str] = mapped_column(ForeignKey('places.id'))
    title: Mapped[str] = mapped_column(String(200))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    source: Mapped[str] = mapped_column(String(200))
    facts: Mapped[str] = mapped_column(Text)
    material_ref: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default='DRAFT')
    disposition: Mapped[str] = mapped_column(Text, default='')
    last_editor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    submitted_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    clue_id: Mapped[str | None] = mapped_column(ForeignKey('clues.id'), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class PlaceEvent(Base):
    __tablename__ = 'place_events'
    __table_args__ = (Index('ix_place_event_created', 'place_id', 'created_at', 'id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    place_id: Mapped[str] = mapped_column(ForeignKey('places.id'))
    resource_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class GeoLocation(Base):
    __tablename__ = 'geo_locations'
    __table_args__ = (
        UniqueConstraint('resource_type', 'resource_id', name='uq_geo_resource'),
        CheckConstraint('(longitude IS NULL AND latitude IS NULL) OR (longitude IS NOT NULL AND latitude IS NOT NULL AND longitude >= -180 AND longitude <= 180 AND latitude >= -85 AND latitude <= 85)', name='ck_geo_coordinates'),
        Index('ix_geo_org_type', 'org_id', 'resource_type'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    resource_type: Mapped[str] = mapped_column(String(20))
    resource_id: Mapped[str] = mapped_column(String(36))
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class GeoLocationEvent(Base):
    __tablename__ = 'geo_location_events'
    __table_args__ = (Index('ix_geo_event_created', 'location_id', 'created_at', 'id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    location_id: Mapped[str] = mapped_column(ForeignKey('geo_locations.id'))
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    snapshot_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
