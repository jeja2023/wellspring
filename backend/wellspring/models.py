from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import String, ForeignKey, Boolean, UniqueConstraint, Text, Integer, Date, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .types import UTCDateTime

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    unit_type: Mapped[str] = mapped_column(String(20), default="OTHER", server_default="OTHER")
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.id"), nullable=True, default="wellspring-business-user")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))

class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())

class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("org_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    number: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)

class CaseInformation(Base):
    __tablename__ = "case_information"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    number: Mapped[str] = mapped_column(String(80), unique=True)
    alarm_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    receiving_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    receiving_branch: Mapped[str | None] = mapped_column(Text, nullable=True)
    alarm_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    alarm_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    caller: Mapped[str | None] = mapped_column(Text, nullable=True)
    alarm_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    caller_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    modification_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    standardized_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    involved_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    apprehended_people: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor_id", "operation", "idempotency_key", name="uq_idempotency_actor_operation_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    operation: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="PROCESSING")
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Clue(Base):
    __tablename__ = "clues"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    reference_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="NORMAL", server_default="NORMAL")
    suggested_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey("clue_import_batches.id"), nullable=True)

class InvestigationTask(Base):
    __tablename__ = "investigation_tasks"
    __table_args__ = (UniqueConstraint("clue_id", name="uq_investigation_task_clue"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    clue_id: Mapped[str] = mapped_column(ForeignKey("clues.id"), index=True)
    objective: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assignee_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    last_submitter_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    result_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)

class IntelligenceEvent(Base):
    __tablename__ = "intelligence_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    clue_id: Mapped[str] = mapped_column(ForeignKey("clues.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("investigation_tasks.id"), nullable=True, index=True)
    related_link_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    assignee_before_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assignee_after_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    before_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    after_status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text)
    result_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClueImportBatch(Base):
    __tablename__ = "clue_import_batches"
    __table_args__ = (Index("ix_clue_import_org_created", "org_id", "created_at", "id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(200))
    content_sha256: Mapped[str] = mapped_column(String(64))
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class ClueCaseLink(Base):
    __tablename__ = "clue_case_links"
    __table_args__ = (
        Index("uq_clue_case_active", "clue_id", "case_id", unique=True,
              sqlite_where=text("status = 'ACTIVE'"), postgresql_where=text("status = 'ACTIVE'")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    clue_id: Mapped[str] = mapped_column(ForeignKey("clues.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    basis: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    version: Mapped[int] = mapped_column(default=1)
    revoked_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PersonDraft(Base):
    __tablename__ = "person_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(200))
    verification_status: Mapped[str] = mapped_column(String(30), default="UNVERIFIED")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    version: Mapped[int] = mapped_column(default=1)
    document_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str] = mapped_column(String(100), default='', server_default='')
    address: Mapped[str] = mapped_column(Text, default='', server_default='')
    responsible_org_id: Mapped[str | None] = mapped_column(ForeignKey('organizations.id'), nullable=True)
    responsible_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)


class CaseRelation(Base):
    __tablename__ = "case_relations"
    __table_args__ = (Index("uq_case_relation_active", "source_case_id", "target_case_id", "relation_type", unique=True, sqlite_where=text("relation_status = 'ACTIVE'"), postgresql_where=text("relation_status = 'ACTIVE'")),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    target_case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(30))
    relation_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    basis: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    revoked_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

class CaseRelationEvent(Base):
    __tablename__ = "case_relation_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    relation_id: Mapped[str] = mapped_column(ForeignKey("case_relations.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    before_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    after_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class PersonCaseCandidate(Base):
    __tablename__ = "person_case_candidates"
    __table_args__ = (Index("uq_person_case_candidate_active", "person_id", "case_id", unique=True, sqlite_where=text("status = 'ACTIVE'"), postgresql_where=text("status = 'ACTIVE'")),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person_drafts.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    basis: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    revoked_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

class PersonCaseCandidateEvent(Base):
    __tablename__ = "person_case_candidate_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("person_case_candidates.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class CaseImportBatch(Base):
    __tablename__ = "case_import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(200))
    digest: Mapped[str] = mapped_column(String(64))
    mapping_version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

class CaseImportRow(Base):
    __tablename__ = "case_import_rows"
    __table_args__ = (UniqueConstraint("batch_id", "line_number", name="uq_case_import_batch_line"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("case_import_batches.id"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    number: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    preview_status: Mapped[str] = mapped_column(String(30))
    result_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True)


# Match the migration indexes used by the scoped queries.
Index('ix_cases_org_created', Case.org_id, Case.created_at, Case.id)
Index('ix_clues_org_created', Clue.org_id, Clue.created_at, Clue.id)
Index('uq_clue_org_reference', Clue.org_id, Clue.reference_no, unique=True)
Index('ix_people_org_created', PersonDraft.org_id, PersonDraft.created_at, PersonDraft.id)
Index('ix_case_information_org_active_created', CaseInformation.org_id, CaseInformation.deleted_at, CaseInformation.created_at, CaseInformation.id)
Index('ix_case_information_active_created', CaseInformation.deleted_at, CaseInformation.created_at, CaseInformation.id)
Index('ix_audit_actor_created', Audit.actor_id, Audit.created_at, Audit.id)
Index('ix_audit_created', Audit.created_at, Audit.id)
Index('ix_sessions_user_id', Session.user_id)
Index('ix_sessions_expires_at', Session.expires_at)
Index('ix_tasks_org_assignee_status', InvestigationTask.org_id, InvestigationTask.assignee_id, InvestigationTask.status, InvestigationTask.due_date, InvestigationTask.id)
Index('ix_tasks_org_review_created', InvestigationTask.org_id, InvestigationTask.status, InvestigationTask.created_at, InvestigationTask.id)

from . import wastewater_models  # Register the independent monitoring tables.
from . import intake_models
from . import access_models
from . import ai_models
from . import intelligence_models
from . import analysis_models
from . import person_models
from . import place_models
