"""Create/associate case drafts explicitly; never infer legal case registration."""
from datetime import datetime, timezone
import json
from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .case_information_schema import CaseInformationFields
from .db import get_db
from .intake_models import IntakeCaseLink as Link
from .models import Case, CaseInformation as Intake, User
from .security import current_user
from .access_policy import effective_permissions


def unique_conflict(exception, constraint, sqlite_message):
    original = exception.orig
    return (getattr(original, "sqlstate", None) == "23505" and
            getattr(getattr(original, "diag", None), "constraint_name", None) == constraint) or str(original) == sqlite_message


class Transfer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_version: int = Field(ge=1)
    mode: Literal["NEW", "EXISTING"]
    number: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    case_id: str | None = Field(default=None, min_length=1, max_length=36)
    basis: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def destination(self):
        if self.mode == "NEW" and (not self.number or not self.title or self.case_id is not None):
            raise ValueError("新建案件须填写编号及名称，不能同时指定已有案件")
        if self.mode == "EXISTING" and (not self.case_id or self.number is not None or self.title is not None):
            raise ValueError("关联已有案件须仅指定目标案件")
        return self


class Revoke(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


def attach_case_links(db, user, identities, items):
    """One bounded lookup for a visible intake page; no per-row lazy queries."""
    if not identities:
        return
    permissions=getattr(user,'_effective_permissions',None)
    if permissions is None:permissions=effective_permissions(db,user)
    rows = db.execute(select(Link, Case).join(Case, Link.case_id == Case.id).join(Intake, Link.intake_id == Intake.id).where(
        Link.intake_id.in_([identity for identity, _org in identities]), Link.status == "ACTIVE",
        Link.org_id == Case.org_id, Link.org_id == Intake.org_id)).all()
    links = {}
    for link, case in rows:
        accessible = link.org_id == user.org_id and 'cases.read' in permissions
        links[link.intake_id] = {"linked": True, "accessible": accessible,
                               **({"id": case.id, "number": case.number, "title": case.title} if accessible else {})}
    for (identity, organization), item in zip(identities, items):
        item["can_link_case"] = organization == user.org_id and {'intake.write','cases.read','cases.write'} <= permissions
        item["case_link"] = links.get(identity)


def create_router(error, audit, reserve, finish, page_result, request_id):
    router = APIRouter(prefix="/api", tags=["接警转办与案件来源（开发验证）"])

    def own_intake(db, user, identity):
        row = db.scalar(select(Intake).where(Intake.id == identity, Intake.org_id == user.org_id))
        if row is None: raise error(404, "NOT_FOUND", "接警信息不存在或无权办理")
        return row

    def own_case(db, user, identity):
        row = db.scalar(select(Case).where(Case.id == identity, Case.org_id == user.org_id))
        if row is None: raise error(404, "NOT_FOUND", "案件不存在或无权访问")
        return row

    @router.post("/case-information/{identity}/case-link", status_code=201)
    def transfer(identity: str, data: Transfer, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
        source = own_intake(db, user, identity)
        target = own_case(db, user, data.case_id) if data.mode == "EXISTING" else None
        record, replay = reserve(db, user, "INTAKE_CASE_LINK", key, {"id": identity, **data.model_dump()})
        if replay: return replay
        if source.deleted_at is not None: raise error(409, "INTAKE_HIDDEN", "接警记录已隐藏，请恢复并核对后再办理")
        changed = db.execute(update(Intake).where(Intake.id == identity, Intake.org_id == user.org_id,
            Intake.version == data.source_version, Intake.deleted_at.is_(None)).values(version=Intake.version + 1))
        if changed.rowcount != 1: raise error(409, "VERSION_CONFLICT", "接警信息已变化，请重新打开并核对")
        if db.scalar(select(Link.id).where(Link.intake_id == identity, Link.status == "ACTIVE")):
            raise error(409, "INTAKE_ALREADY_LINKED", "此接警信息已关联案件，请查看原案件，不能重复创建")
        if target is None:
            target = Case(org_id=user.org_id, number=data.number, title=data.title)
            db.add(target)
            try: db.flush()
            except IntegrityError as exception:
                db.rollback()
                if unique_conflict(exception, "cases_org_id_number_key", "UNIQUE constraint failed: cases.org_id, cases.number"):
                    raise error(409, "DUPLICATE_CASE_NUMBER", "本组织已有此案件编号，请核对后选择关联已有案件")
                raise
            audit(db, user, "CASE_CREATE_FROM_INTAKE", target.id)
        snapshot = CaseInformationFields(**{name: getattr(source, name) for name in CaseInformationFields.model_fields}).model_dump(by_alias=True)
        link = Link(org_id=user.org_id, intake_id=identity, case_id=target.id, source_version=data.source_version,
                    source_number=source.number, source_snapshot=json.dumps(snapshot, ensure_ascii=False),
                    created_case=data.mode == "NEW", basis=data.basis, created_by=user.id)
        db.add(link)
        try: db.flush()
        except IntegrityError as exception:
            db.rollback()
            if unique_conflict(exception, "uq_intake_case_active", "UNIQUE constraint failed: intake_case_links.intake_id"):
                raise error(409, "INTAKE_ALREADY_LINKED", "此接警信息已关联案件，请重新查询")
            raise
        result = {"link_id": link.id, "id": target.id, "number": target.number, "title": target.title,
                  "created_case": link.created_case, "source_version": data.source_version + 1}
        audit(db, user, "INTAKE_CASE_LINK", link.id)
        finish(record, result, 201, link.id); db.commit(); return result

    @router.get("/cases/{case_id}/intake-sources")
    def sources(case_id: str, request: Request, page: int = Query(1, ge=1, le=100000), page_size: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        own_case(db, user, case_id)
        stmt = select(Link, User.username, Intake.deleted_at).join(User, Link.created_by == User.id).join(Intake, Link.intake_id == Intake.id).where(Link.case_id == case_id, Link.org_id == user.org_id, Intake.org_id == user.org_id)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(stmt.order_by(Link.created_at.desc(), Link.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        items = [{"id": row.id, "source_number": row.source_number, "source_version": row.source_version,
                  "basis": row.basis, "created_case": row.created_case, "created_at": row.created_at, "created_by": author,
                  "source_hidden": deleted_at is not None, "status": row.status, "version": row.version,
                  "revoke_reason": row.revoke_reason} for row, author, deleted_at in rows]
        audit(db, user, "CASE_INTAKE_SOURCES_VIEW", case_id); db.commit()
        return page_result(items, page, page_size, total, request_id(request))

    def own_link(db, user, case_id, link_id):
        own_case(db, user, case_id)
        row = db.scalar(select(Link).where(Link.id == link_id, Link.case_id == case_id, Link.org_id == user.org_id))
        if row is None: raise error(404, "NOT_FOUND", "来源记录不存在或无权访问")
        return row

    @router.get("/cases/{case_id}/intake-sources/{link_id}")
    def snapshot(case_id: str, link_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = own_link(db, user, case_id, link_id)
        audit(db, user, "CASE_INTAKE_SNAPSHOT_VIEW", link_id); db.commit()
        return {"id": row.id, "source_number": row.source_number, "source_version": row.source_version,
                "status": row.status, "fields": json.loads(row.source_snapshot)}

    @router.post("/cases/{case_id}/intake-sources/{link_id}/revoke")
    def revoke(case_id: str, link_id: str, data: Revoke, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
        row = own_link(db, user, case_id, link_id)
        own_intake(db, user, row.intake_id)
        record, replay = reserve(db, user, "INTAKE_CASE_REVOKE", key, {"id": link_id, **data.model_dump()})
        if replay: return replay
        # Use the same lock order as conversion: intake first, relation second.
        db.execute(update(Intake).where(Intake.id == row.intake_id, Intake.org_id == user.org_id).values(version=Intake.version + 1))
        changed = db.execute(update(Link).where(Link.id == link_id, Link.org_id == user.org_id, Link.version == data.version,
            Link.status == "ACTIVE").values(status="REVOKED", version=Link.version + 1, revoked_by=user.id,
                                             revoked_at=datetime.now(timezone.utc), revoke_reason=data.reason))
        if changed.rowcount != 1: raise error(409, "VERSION_OR_STATE_CONFLICT", "关联已变化或已撤销，请重新查看")
        audit(db, user, "INTAKE_CASE_REVOKE", link_id)
        result = {"id": link_id, "status": "REVOKED", "version": data.version + 1}
        finish(record, result, 200, link_id); db.commit(); return result

    return router
