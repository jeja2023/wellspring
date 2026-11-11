"""Organization-to-organization clue deliveries and feedback chain."""
from datetime import date, datetime
from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import now, uid
from .types import UTCDateTime


class ClueDelivery(Base):
    __tablename__ = 'clue_deliveries'
    __table_args__ = (
        Index('ix_delivery_recipient_status', 'recipient_org_id', 'status', 'created_at', 'id'),
        Index('ix_delivery_sender_created', 'sender_org_id', 'created_at', 'id'),
        Index('ix_delivery_parent', 'parent_id'),
        Index('uq_delivery_active_destination','clue_id','recipient_org_id',unique=True,
            sqlite_where=text("status != 'CLOSED'"),postgresql_where=text("status != 'CLOSED'")),
    )
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    clue_id: Mapped[str] = mapped_column(ForeignKey('clues.id'))
    parent_id: Mapped[str|None] = mapped_column(ForeignKey('clue_deliveries.id'),nullable=True)
    sender_org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    recipient_org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    sender_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    assignee_id: Mapped[str|None] = mapped_column(ForeignKey('users.id'),nullable=True)
    objective: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date|None] = mapped_column(Date,nullable=True)
    allow_station: Mapped[bool] = mapped_column(Boolean,default=False)
    snapshot_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30),default='OPEN')
    disposition_text: Mapped[str] = mapped_column(Text,default='')
    feedback_text: Mapped[str] = mapped_column(Text,default='')
    result_code: Mapped[str|None] = mapped_column(String(30),nullable=True)
    version: Mapped[int] = mapped_column(Integer,default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(),default=now)
    accepted_at: Mapped[datetime|None] = mapped_column(UTCDateTime(),nullable=True)
    feedback_at: Mapped[datetime|None] = mapped_column(UTCDateTime(),nullable=True)
    closed_at: Mapped[datetime|None] = mapped_column(UTCDateTime(),nullable=True)


class DeliveryEvent(Base):
    __tablename__='clue_delivery_events'
    __table_args__=(Index('ix_delivery_event_created','delivery_id','created_at','id'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    delivery_id: Mapped[str] = mapped_column(ForeignKey('clue_deliveries.id'))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    actor_org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    action: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text)
    before_status: Mapped[str|None] = mapped_column(String(30),nullable=True)
    after_status: Mapped[str] = mapped_column(String(30))
    payload_json: Mapped[str|None] = mapped_column(Text,nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(),default=now)
