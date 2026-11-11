"""接警信息开发接口。组织过滤尚不能替代正式权限与字段授权。"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .case_information_schema import CaseInformationFields
from .db import get_db
from .models import CaseInformation, Organization, User
from .security import current_admin, current_user
from .intake_cases import attach_case_links

MAX_TRANSFER_CHARACTERS = 2_000_000
SUMMARY_FIELDS = (
    "number", "alarm_type", "receiving_unit", "receiving_branch", "alarm_content",
    "alarm_address", "alarm_time", "additional_result", "standardized_address",
    "category", "result", "involved_items", "apprehended_people",
)


class Search(BaseModel):
    keyword: str = Field(default="", max_length=200)
    alarm_type: str = Field(default="", max_length=10000)
    result: str = Field(default="", max_length=10000)
    include_summary: bool = True
    summary_only: bool = False
    include_case_links: bool = False
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=20, ge=1, le=100)


class ImportBatch(BaseModel):
    rows: list[CaseInformationFields] = Field(min_length=1, max_length=1000)


class UpdateInput(BaseModel):
    version: int = Field(ge=1)
    fields: CaseInformationFields


class DeleteInput(BaseModel):
    version: int = Field(ge=1)


def create_router(error, audit, reserve, finish, page_result, request_id):
    router = APIRouter(prefix="/api/case-information", tags=["接警信息（开发验证）"])

    def as_json(row):
        values = {name: getattr(row, name) for name in CaseInformationFields.model_fields}
        return {"id": row.id, "version": row.version, **CaseInformationFields(**values).model_dump(by_alias=True)}

    def access_scope(user):
        return [] if user.is_admin else [CaseInformation.org_id == user.org_id]

    def visible(db, user, item_id):
        row = db.scalar(select(CaseInformation).where(CaseInformation.id == item_id, *access_scope(user), CaseInformation.deleted_at.is_(None)))
        if not row:
            raise error(404, "NOT_FOUND", "记录不存在或无权访问")
        return row

    def filters(data, user):
        conditions = [*access_scope(user), CaseInformation.deleted_at.is_(None)]
        keyword = data.keyword.strip()
        if keyword:
            conditions.append(or_(*(getattr(CaseInformation, name).contains(keyword, autoescape=True) for name in CaseInformationFields.model_fields)))
        if data.alarm_type:
            conditions.append(CaseInformation.alarm_type == data.alarm_type)
        if data.result:
            conditions.append(CaseInformation.result == data.result)
        return conditions

    @router.post("/search")
    def search(data: Search, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
        conditions = filters(data, user)
        stmt = select(CaseInformation).where(*conditions)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        if data.summary_only:
            # Project and shorten in SQL so hidden fields and full long text do
            # not travel from the database. No lazy per-row ORM loads are used.
            columns = [CaseInformation.id, CaseInformation.version, CaseInformation.org_id]
            for name in SUMMARY_FIELDS:
                column = getattr(CaseInformation, name)
                columns.append((column if name == "number" else func.substr(column, 1, 200)).label(name))
            summary_stmt = select(*columns).where(*conditions).order_by(CaseInformation.created_at.desc(), CaseInformation.id.desc()).offset((data.page - 1) * data.page_size).limit(data.page_size)
            rows = db.execute(summary_stmt).mappings().all()
            items = [{"id": row["id"], "version": row["version"], "is_summary": True,
                      **{CaseInformationFields.model_fields[name].alias: row[name] for name in SUMMARY_FIELDS}}
                     for row in rows]
        else:
            rows = db.scalars(stmt.order_by(CaseInformation.created_at.desc(), CaseInformation.id.desc()).offset((data.page - 1) * data.page_size).limit(data.page_size)).all()
            items = [as_json(row) for row in rows]
        if data.include_case_links:
            identities = [(row["id"], row["org_id"]) for row in rows] if data.summary_only else [(row.id, row.org_id) for row in rows]
            attach_case_links(db, user, identities, items)
        def counts(column):
            return [{"label": label or "（未填写）", "count": count} for label, count in db.execute(select(column, func.count()).where(*conditions).group_by(column).order_by(func.count().desc(), column)).all()]
        response = page_result(items, data.page, data.page_size, total, request_id(request))
        if data.include_summary:
            response["statistics"] = {"types": counts(CaseInformation.alarm_type), "results": counts(CaseInformation.result)}
            scope = [*access_scope(user), CaseInformation.deleted_at.is_(None)]
            response["options"] = {
                "types": [value for value in db.scalars(select(CaseInformation.alarm_type).where(*scope, CaseInformation.alarm_type.is_not(None), CaseInformation.alarm_type != "").distinct().order_by(CaseInformation.alarm_type)).all()],
                "results": [value for value in db.scalars(select(CaseInformation.result).where(*scope, CaseInformation.result.is_not(None), CaseInformation.result != "").distinct().order_by(CaseInformation.result)).all()],
            }
        audit(db, user, "CASE_INFORMATION_SEARCH", user.org_id); db.commit()
        return response

    @router.get("/{item_id}/detail")
    def detail(item_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = visible(db, user, item_id)
        result = {**as_json(row), "is_summary": False}
        attach_case_links(db, user, [(row.id, row.org_id)], [result])
        audit(db, user, "CASE_INFORMATION_VIEW", item_id)
        db.commit()
        return result

    @router.post("/export")
    def export(data: Search, user: User = Depends(current_user), db: Session = Depends(get_db)):
        stmt = select(CaseInformation).where(*filters(data, user)).order_by(CaseInformation.created_at.desc(), CaseInformation.id.desc()).limit(1001)
        items = []
        characters = 0
        rows = db.scalars(stmt.execution_options(yield_per=10))
        try:
            for row in rows:
                if len(items) >= 1000:
                    raise error(422, "EXPORT_TOO_LARGE", "当前结果超过 1000 条，请缩小筛选范围")
                item = as_json(row)
                characters += sum(len(value) for value in item.values() if isinstance(value, str))
                if characters > MAX_TRANSFER_CHARACTERS:
                    raise error(422, "EXPORT_TOO_LARGE", "导出内容过大，请缩小筛选范围")
                items.append(item)
        finally:
            rows.close()
        audit(db, user, "CASE_INFORMATION_EXPORT", user.org_id); db.commit()
        return {"items": items}

    @router.post("/import", status_code=201)
    def import_rows(data: ImportBatch, key: str | None = Header(None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        payload = [row.model_dump() for row in data.rows]
        if sum(len(value or "") for row in payload for value in row.values()) > MAX_TRANSFER_CHARACTERS:
            raise error(422, "IMPORT_TOO_LARGE", "导入数据过大")
        numbers = [row["number"] for row in payload]
        if len(set(numbers)) != len(numbers):
            raise error(409, "DUPLICATE_NUMBER", "导入文件中存在重复接警编号")
        idempotency, replay = reserve(db, user, "CASE_INFORMATION_IMPORT", key, {"rows": payload})
        if replay: return replay
        if db.scalar(select(CaseInformation.id).where(CaseInformation.number.in_(numbers)).limit(1)):
            raise error(409, "DUPLICATE_NUMBER", "接警编号已存在或曾被删除，整批未导入")
        try:
            for row in payload:
                db.add(CaseInformation(org_id=user.org_id, created_by=user.id, **row))
            db.flush()
        except IntegrityError:
            db.rollback()
            raise error(409, "DUPLICATE_NUMBER", "接警编号已存在，整批未导入")
        audit(db, user, "CASE_INFORMATION_IMPORT", user.org_id)
        result = {"created": len(payload)}
        finish(idempotency, result, 201); db.commit()
        return result

    @router.post("/{item_id}/update")
    def update_item(item_id: str, data: UpdateInput, key: str | None = Header(None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        values = data.fields.model_dump()
        visible(db, user, item_id)
        idempotency, replay = reserve(db, user, "CASE_INFORMATION_UPDATE", key, {"id": item_id, "version": data.version, "fields": values})
        if replay: return replay
        try:
            changed = db.execute(update(CaseInformation).where(CaseInformation.id == item_id, *access_scope(user), CaseInformation.deleted_at.is_(None), CaseInformation.version == data.version).values(**values, version=CaseInformation.version + 1))
        except IntegrityError:
            db.rollback()
            raise error(409, "DUPLICATE_NUMBER", "接警编号已存在或曾被删除")
        if changed.rowcount != 1: raise error(409, "VERSION_CONFLICT", "记录已发生变化，请刷新后重试")
        audit(db, user, "CASE_INFORMATION_UPDATE", item_id)
        result = {"id": item_id, "version": data.version + 1}
        finish(idempotency, result, 200, item_id); db.commit(); return result

    @router.post("/{item_id}/delete")
    def delete_item(item_id: str, data: DeleteInput, key: str | None = Header(None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        # Reauthorize even a replay; a previously deleted row remains replayable.
        if not db.scalar(select(CaseInformation.id).where(CaseInformation.id == item_id, *access_scope(user))):
            raise error(404, "NOT_FOUND", "记录不存在或无权访问")
        idempotency, replay = reserve(db, user, "CASE_INFORMATION_DELETE", key, {"id": item_id, "version": data.version})
        if replay: return replay
        visible(db, user, item_id)
        changed = db.execute(update(CaseInformation).where(CaseInformation.id == item_id, *access_scope(user), CaseInformation.deleted_at.is_(None), CaseInformation.version == data.version).values(deleted_at=datetime.now(timezone.utc), version=CaseInformation.version + 1))
        if changed.rowcount != 1: raise error(409, "VERSION_CONFLICT", "记录已发生变化，请刷新后重试")
        audit(db, user, "CASE_INFORMATION_DELETE", item_id)
        result = {"id": item_id, "deleted": True}
        finish(idempotency, result, 200, item_id); db.commit(); return result

    @router.post("/admin/deleted")
    def deleted_records(data: Search, request: Request, user: User = Depends(current_admin), db: Session = Depends(get_db)):
        stmt = select(CaseInformation, Organization.name).join(Organization, CaseInformation.org_id == Organization.id).where(CaseInformation.deleted_at.is_not(None))
        if data.keyword.strip():
            stmt = stmt.where(CaseInformation.number.contains(data.keyword.strip(), autoescape=True))
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(stmt.order_by(CaseInformation.deleted_at.desc(), CaseInformation.id.desc()).offset((data.page - 1) * data.page_size).limit(data.page_size)).all()
        result = [{"id": row.id, "version": row.version, "number": row.number, "organization": org, "deleted_at": row.deleted_at} for row, org in rows]
        audit(db, user, "CASE_INFORMATION_DELETED_VIEW", user.id); db.commit()
        return page_result(result, data.page, data.page_size, total, request_id(request))

    @router.post("/admin/{item_id}/restore")
    def restore(item_id: str, data: DeleteInput, key: str | None = Header(None, alias="Idempotency-Key"), user: User = Depends(current_admin), db: Session = Depends(get_db)):
        idempotency, replay = reserve(db, user, "CASE_INFORMATION_RESTORE", key, {"id": item_id, "version": data.version})
        if replay: return replay
        row = db.scalar(select(CaseInformation).where(CaseInformation.id == item_id, CaseInformation.deleted_at.is_not(None)))
        if not row: raise error(404, "NOT_FOUND", "记录不存在或未被删除")
        changed = db.execute(update(CaseInformation).where(CaseInformation.id == item_id, CaseInformation.deleted_at.is_not(None), CaseInformation.version == data.version).values(deleted_at=None, version=CaseInformation.version + 1))
        if changed.rowcount != 1: raise error(409, "VERSION_CONFLICT", "记录已发生变化，请刷新后重试")
        audit(db, user, "CASE_INFORMATION_RESTORE", item_id)
        result = {"id": item_id, "restored": True}
        finish(idempotency, result, 200, item_id); db.commit(); return result
    return router
