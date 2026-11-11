from __future__ import annotations

import hashlib
import json
import re
import logging
from time import perf_counter
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from .db import get_db
from .models import Audit, Case, IdempotencyRecord, Organization, Session, User
from .http_limits import RequestBudgetMiddleware, login_limiter
from .access_policy import identity_json
from .security import DUMMY_PASSWORD_HASH, PASSWORD_MAX_LENGTH, USERNAME_MAX_LENGTH, current_admin, current_user, new_token, token_hash, verify_password

app = FastAPI(title="清源开发验证 API", version="0.0.6")
app.add_middleware(RequestBudgetMiddleware)

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=USERNAME_MAX_LENGTH)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)

class CaseCreate(BaseModel):
    number: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)


SORTABLE_CASES = {"created_at": Case.created_at, "number": Case.number, "title": Case.title}
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,120}$")


def api_error(status_code: int, code: str, message: str, details: list[dict[str, Any]] | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "details": details or []})


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown-request")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    candidate = request.headers.get("X-Request-ID", "")
    rid = candidate if re.fullmatch(r"[A-Za-z0-9._:-]{8,64}", candidate) else str(uuid4())
    request.state.request_id = rid
    started = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    logging.getLogger("wellspring.requests").info(
        "request_complete request_id=%s status=%s duration_ms=%.1f",
        rid, response.status_code, (perf_counter() - started) * 1000,
    )
    return response


def error_body(request: Request, status_code: int, detail: Any) -> dict[str, Any]:
    if isinstance(detail, dict):
        code = str(detail.get("code", "HTTP_ERROR"))
        message = str(detail.get("message", "请求未完成"))
        details = detail.get("details", [])
    else:
        code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR"}.get(status_code, "HTTP_ERROR")
        message = str(detail) if detail else "请求未完成"
        details = []
    return {"code": code, "message": message, "details": details, "request_id": request_id(request)}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content=error_body(request, exc.status_code, exc.detail), headers={**(exc.headers or {}), "X-Request-ID": request_id(request)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item.get("loc", []) if part != "body") or "request"
        details.append({"field": location, "code": "INVALID_VALUE", "message": "字段格式或取值不正确"})
    return JSONResponse(status_code=422, content=error_body(request, 422, {"code": "VALIDATION_ERROR", "message": "请检查填写的信息", "details": details}), headers={"X-Request-ID": request_id(request)})


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logging.getLogger("wellspring").error("request_failed request_id=%s exception_type=%s", request_id(request), type(exc).__name__)
    return JSONResponse(status_code=500, content=error_body(request, 500, {"code": "INTERNAL_ERROR", "message": "服务暂时不可用，请联系管理员并提供请求编号", "details": []}), headers={"X-Request-ID": request_id(request)})


def audit(db: DBSession, user: User, action: str, object_id: str):
    db.add(Audit(actor_id=user.id, org_id=user.org_id, action=action, object_id=object_id))


def case_json(case: Case) -> dict[str, Any]:
    return {"id": case.id, "number": case.number, "title": case.title, "status": case.status, "created_at": case.created_at}


def page_result(items: list[dict[str, Any]], page: int, page_size: int, total: int, rid: str) -> dict[str, Any]:
    return {"items": items, "page": page, "page_size": page_size, "total": total, "has_more": page * page_size < total, "request_id": rid}


def request_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def replay_idempotency(record: IdempotencyRecord, digest: str) -> JSONResponse | None:
    if record.request_hash != digest:
        raise api_error(409, "IDEMPOTENCY_CONFLICT", "同一幂等键对应了不同请求")
    if record.status == "SUCCEEDED" and record.response_json and record.status_code:
        return JSONResponse(status_code=record.status_code, content=json.loads(record.response_json), headers={"X-Idempotent-Replay": "true"})
    raise api_error(409, "IDEMPOTENCY_IN_PROGRESS", "相同操作正在处理中，请查询原请求结果")


def reserve_idempotency(db: DBSession, user: User, operation: str, key: str | None, payload: dict[str, Any]) -> tuple[IdempotencyRecord, JSONResponse | None]:
    if not key:
        raise api_error(400, "IDEMPOTENCY_KEY_REQUIRED", "写操作需要 Idempotency-Key")
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise api_error(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key 长度应为 8 至 120 个字符，且只能包含字母、数字和 . _ : -")
    digest = request_digest({"org_id": user.org_id, "payload": payload})
    existing = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor_id == user.id, IdempotencyRecord.operation == operation, IdempotencyRecord.idempotency_key == key))
    if existing:
        replay = replay_idempotency(existing, digest)
        if replay:
            return existing, replay
    record = IdempotencyRecord(actor_id=user.id, operation=operation, idempotency_key=key, request_hash=digest, status="PROCESSING")
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor_id == user.id, IdempotencyRecord.operation == operation, IdempotencyRecord.idempotency_key == key))
        if existing:
            replay = replay_idempotency(existing, digest)
            if replay:
                return existing, replay
        raise api_error(409, "IDEMPOTENCY_CONFLICT", "操作正在处理中，请稍后查询")
    return record, None


def finish_idempotency(record: IdempotencyRecord, payload: dict[str, Any], status_code: int, resource_id: str | None = None):
    record.status = "SUCCEEDED"
    record.status_code = status_code
    record.response_json = json.dumps(jsonable_encoder(payload), ensure_ascii=False, separators=(",", ":"))
    record.resource_id = resource_id
    record.completed_at = datetime.now(timezone.utc)


def sorted_statement(stmt, mapping: dict[str, Any], sort: str, order: Literal["asc", "desc"], identity: Any):
    if sort not in mapping:
        raise api_error(422, "VALIDATION_ERROR", "不支持的排序字段")
    column = mapping[sort]
    stmt = stmt.order_by(column.asc() if order == "asc" else column.desc())
    return stmt.order_by(identity.asc() if order == "asc" else identity.desc())


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "development", "version": app.version}


@lru_cache(maxsize=1)
def expected_schema_heads():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    return set(ScriptDirectory.from_config(config).get_heads())


@app.get("/api/ready")
def readiness(db: DBSession = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        current = set(db.scalars(text("SELECT version_num FROM alembic_version")))
        if current != expected_schema_heads():
            raise ValueError("schema version mismatch")
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}


@app.post("/api/login")
def login(data: Login, request: Request, db: DBSession = Depends(get_db)):
    peer = request.client.host if request.client else "unknown"
    if not login_limiter.allow(peer, data.username):
        raise HTTPException(status_code=429, detail={"code": "LOGIN_RATE_LIMITED", "message": "登录尝试过于频繁，请稍后再试", "details": []}, headers={"Retry-After": str(login_limiter.retry_after_seconds())})
    user = db.scalar(select(User).where(User.username == data.username))
    valid_password = verify_password(data.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    organization = db.get(Organization,user.org_id) if user else None
    if not user or not user.active or not organization or not organization.active or not valid_password:
        raise api_error(401, "UNAUTHENTICATED", "账号或密码错误")
    token = new_token()
    db.execute(delete(Session).where(Session.expires_at <= datetime.now(timezone.utc)))
    db.add(Session(token_hash=token_hash(token), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=8)))
    audit(db, user, "LOGIN", user.id)
    db.commit()
    organization = db.get(Organization, user.org_id)
    return {"token": token, **identity_json(db,user,organization)}


@app.post("/api/logout")
def logout(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, user, "LOGOUT", user.id)
    db.commit()
    return {"ok": True}


@app.get("/api/session")
def session_info(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    organization = db.get(Organization, user.org_id)
    return identity_json(db,user,organization)


@app.get("/api/admin/status")
def admin_status(user: User = Depends(current_admin)):
    return {"username": user.username, "is_admin": True}


class SystemAuditSearch(BaseModel):
    username: str = Field(default="", max_length=80)
    action: str = Field(default="", max_length=80)
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=20, ge=1, le=100)


@app.post("/api/admin/audit/search")
def search_system_audit(data: SystemAuditSearch, request: Request, user: User = Depends(current_admin), db: DBSession = Depends(get_db)):
    stmt = select(Audit, User.username, Organization.name).join(User, Audit.actor_id == User.id).join(Organization, Audit.org_id == Organization.id)
    if data.username.strip():
        stmt = stmt.where(User.username.contains(data.username.strip(), autoescape=True))
    if data.action.strip():
        stmt = stmt.where(Audit.action.contains(data.action.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Audit.created_at.desc(), Audit.id.desc()).offset((data.page - 1) * data.page_size).limit(data.page_size)).all()
    items = [{"id": event.id, "username": username, "organization": org_name, "action": event.action, "object_id": event.object_id, "created_at": event.created_at} for event, username, org_name in rows]
    audit(db, user, "SYSTEM_AUDIT_SEARCH", user.id)
    db.commit()
    return page_result(items, data.page, data.page_size, total, request_id(request))


@app.get("/api/cases")
def list_cases(
    request: Request,
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    user: User = Depends(current_user),
    db: DBSession = Depends(get_db),
):
    stmt = select(Case).where(Case.org_id == user.org_id)
    if q.strip():
        term = q.strip()
        stmt = stmt.where((Case.title.contains(term, autoescape=True)) | (Case.number.contains(term, autoescape=True)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(sorted_statement(stmt, SORTABLE_CASES, sort, order, Case.id).offset((page - 1) * page_size).limit(page_size)).all()
    audit(db, user, "CASE_LIST", user.org_id)
    db.commit()
    return page_result([case_json(case) for case in rows], page, page_size, total, request_id(request))


@app.post("/api/cases", status_code=201)
def create_case(
    data: CaseCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(current_user),
    db: DBSession = Depends(get_db),
):
    number, title = data.number.strip(), data.title.strip()
    if not number or not title:
        raise api_error(422, "VALIDATION_ERROR", "编号和名称不能为空")
    record, replay = reserve_idempotency(db, user, "CASE_CREATE", idempotency_key, {"number": number, "title": title})
    if replay:
        return replay
    case = Case(org_id=user.org_id, number=number, title=title)
    db.add(case)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise api_error(409, "DUPLICATE_CASE_NUMBER", "本组织内案件编号已存在")
    payload = case_json(case)
    audit(db, user, "CASE_CREATE", case.id)
    finish_idempotency(record, payload, 201, case.id)
    db.commit()
    return payload


from .intelligence import create_router as create_intelligence_router
app.include_router(create_intelligence_router(api_error, audit, reserve_idempotency, finish_idempotency, page_result, request_id))

from .clue_case_links import create_router as create_clue_case_links_router
app.include_router(create_clue_case_links_router(api_error, audit, reserve_idempotency, finish_idempotency, page_result, request_id))


from .person_transfers import create_router as create_person_transfers_router
app.include_router(create_person_transfers_router(api_error,audit,reserve_idempotency,finish_idempotency,page_result,request_id))
from .person_records import create_router as create_person_records_router
app.include_router(create_person_records_router(api_error,audit,reserve_idempotency,finish_idempotency,page_result,request_id))
from .person_drafts import create_router as create_person_drafts_router
app.include_router(create_person_drafts_router(api_error, audit, reserve_idempotency, finish_idempotency, page_result, request_id))

from .case_relations import create_router as create_case_relations_router
app.include_router(create_case_relations_router(api_error, audit, reserve_idempotency, finish_idempotency, page_result, request_id))

from .person_case_candidates import create_router as create_person_case_candidates_router
app.include_router(create_person_case_candidates_router(api_error, audit, reserve_idempotency, finish_idempotency, page_result, request_id))


from .development_tools import create_router as create_development_tools_router
app.include_router(create_development_tools_router(api_error, audit, page_result, request_id))

from .case_imports import create_router as create_case_imports_router
app.include_router(create_case_imports_router(api_error, audit, reserve_idempotency, finish_idempotency, page_result, request_id))


from .case_information import create_router as create_case_information_router
app.include_router(create_case_information_router(api_error, audit, reserve_idempotency, finish_idempotency, page_result, request_id))

from .wastewater import create_router as create_wastewater_router
app.include_router(create_wastewater_router(api_error, audit, reserve_idempotency, finish_idempotency, page_result, request_id))

from .intake_cases import create_router as create_intake_cases_router
app.include_router(create_intake_cases_router(api_error, audit, reserve_idempotency, finish_idempotency, page_result, request_id))

from .administration import create_router as create_administration_router
app.include_router(create_administration_router(api_error,audit,reserve_idempotency,finish_idempotency,page_result,request_id))

from .dashboard import create_router as create_dashboard_router
app.include_router(create_dashboard_router(audit))
from .ai import create_router as create_ai_router
app.include_router(create_ai_router(api_error,audit,reserve_idempotency,finish_idempotency,page_result,request_id))

from .clue_deliveries import create_router as create_clue_deliveries_router
app.include_router(create_clue_deliveries_router(api_error,audit,reserve_idempotency,finish_idempotency,page_result,request_id))
from .clue_imports import create_router as create_clue_import_router
app.include_router(create_clue_import_router(api_error,audit,reserve_idempotency,finish_idempotency,page_result,request_id))

from .analysis_assets import create_router as create_analysis_router
app.include_router(create_analysis_router(api_error,audit,reserve_idempotency,finish_idempotency,page_result,request_id))

from .places import create_router as create_places_router
app.include_router(create_places_router(api_error,audit,reserve_idempotency,finish_idempotency,page_result,request_id))
from .geography import create_router as create_geography_router
app.include_router(create_geography_router(api_error,audit,reserve_idempotency,finish_idempotency,page_result,request_id))
