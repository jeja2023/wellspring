"""Separate subject identity, legal/business episodes, tasks and custody transfers."""
from datetime import date,datetime
from sqlalchemy import Date,ForeignKey,Index,Integer,String,Text,text
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import now,uid
from .types import UTCDateTime


class PersonRecord(Base):
    __tablename__='person_records'
    __table_args__=(Index('ix_person_record_scope_kind','person_id','org_id','kind','verification_status','created_at','id'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    person_id:Mapped[str]=mapped_column(ForeignKey('person_drafts.id'))
    org_id:Mapped[str]=mapped_column(ForeignKey('organizations.id'))
    manager_org_id:Mapped[str]=mapped_column(ForeignKey('organizations.id'))
    kind:Mapped[str]=mapped_column(String(30))
    record_type:Mapped[str]=mapped_column(String(40))
    occurred_on:Mapped[date]=mapped_column(Date)
    source:Mapped[str]=mapped_column(String(200))
    document_no:Mapped[str]=mapped_column(String(200))
    basis:Mapped[str]=mapped_column(Text)
    details_json:Mapped[str]=mapped_column(Text)
    case_id:Mapped[str|None]=mapped_column(ForeignKey('cases.id'),nullable=True)
    replaces_id:Mapped[str|None]=mapped_column(ForeignKey('person_records.id'),nullable=True)
    verification_status:Mapped[str]=mapped_column(String(20),default='PENDING')
    state:Mapped[str]=mapped_column(String(30),default='RECORDED')
    expected_end_on:Mapped[date|None]=mapped_column(Date,nullable=True)
    actual_start_on:Mapped[date|None]=mapped_column(Date,nullable=True)
    actual_end_on:Mapped[date|None]=mapped_column(Date,nullable=True)
    created_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    updated_by:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    verified_by:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    verified_at:Mapped[datetime|None]=mapped_column(UTCDateTime(),nullable=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=now)


class PersonEvent(Base):
    __tablename__='person_events'
    __table_args__=(Index('ix_person_event_created','person_id','created_at','id'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    person_id:Mapped[str]=mapped_column(ForeignKey('person_drafts.id'))
    record_id:Mapped[str|None]=mapped_column(ForeignKey('person_records.id'),nullable=True)
    org_id:Mapped[str]=mapped_column(ForeignKey('organizations.id'))
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(40))
    note:Mapped[str]=mapped_column(Text)
    payload_json:Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=now)


class PersonTask(Base):
    __tablename__='person_tasks'
    __table_args__=(Index('ix_person_task_org_due','org_id','status','due_on','id'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    person_id:Mapped[str]=mapped_column(ForeignKey('person_drafts.id'))
    record_id:Mapped[str|None]=mapped_column(ForeignKey('person_records.id'),nullable=True)
    org_id:Mapped[str]=mapped_column(ForeignKey('organizations.id'))
    task_type:Mapped[str]=mapped_column(String(30))
    title:Mapped[str]=mapped_column(String(200))
    due_on:Mapped[date]=mapped_column(Date)
    status:Mapped[str]=mapped_column(String(20),default='OPEN')
    result_note:Mapped[str]=mapped_column(Text,default='')
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    completed_by:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    completed_at:Mapped[datetime|None]=mapped_column(UTCDateTime(),nullable=True)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=now)


class PersonTransfer(Base):
    __tablename__='person_transfers'
    __table_args__=(Index('ix_person_transfer_target','target_org_id','status','created_at','id'),
        Index('uq_person_transfer_pending','person_id',unique=True,sqlite_where=text("status='PENDING'"),postgresql_where=text("status='PENDING'")),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    person_id:Mapped[str]=mapped_column(ForeignKey('person_drafts.id'))
    source_org_id:Mapped[str]=mapped_column(ForeignKey('organizations.id'))
    target_org_id:Mapped[str]=mapped_column(ForeignKey('organizations.id'))
    requested_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    accepted_by:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    reason:Mapped[str]=mapped_column(Text)
    response_note:Mapped[str]=mapped_column(Text,default='')
    status:Mapped[str]=mapped_column(String(20),default='PENDING')
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=now)
    completed_at:Mapped[datetime|None]=mapped_column(UTCDateTime(),nullable=True)
