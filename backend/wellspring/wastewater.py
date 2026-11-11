"""Wastewater monitoring slice: source observations and review, without user-count inference."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
from typing import Literal
from fastapi import APIRouter, Depends, Header, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import User
from .security import current_user
from .wastewater_models import WastewaterSite as Site, WastewaterSample as Sample, WastewaterResult as Result, WastewaterResultEvent as Event


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SiteInput(Input):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    district: str = Field(min_length=1, max_length=200)
    plant_name: str = Field(default="", max_length=200)
    catchment: str = Field(default="", max_length=1000)


class SiteState(Input):
    version: int = Field(ge=1)
    active: bool
    reason: str = Field(min_length=1, max_length=1000)


class SampleInput(Input):
    code: str = Field(min_length=1, max_length=80)
    site_id: str = Field(min_length=1, max_length=36)
    sampled_at: AwareDatetime
    sampling_method: Literal["GRAB", "COMPOSITE"]
    collector: str = Field(min_length=1, max_length=100)
    flow_m3_day: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=6)
    quality: Literal["VALID", "FLAGGED"]
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def quality_note(self):
        if self.quality == "FLAGGED" and not self.note:
            raise ValueError("质量存疑样本必须填写原因")
        return self


class ResultFields(Input):
    analyte: str = Field(min_length=1, max_length=120)
    detection: Literal["QUANTIFIED", "BELOW_LOQ", "NOT_DETECTED"]
    concentration: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=6)
    quantification_limit: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=6)
    laboratory: str = Field(min_length=1, max_length=200)
    analysis_method: str = Field(min_length=1, max_length=200)
    report_number: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def result_consistency(self):
        if self.detection == "QUANTIFIED":
            if self.concentration is None or (self.quantification_limit is not None and self.concentration < self.quantification_limit):
                raise ValueError("定量结果须提供不低于所填定量限的浓度")
        elif self.concentration is not None:
            raise ValueError("未检出和低于定量限不能填写为零或其他定量浓度")
        if self.detection == "BELOW_LOQ" and self.quantification_limit is None:
            raise ValueError("低于定量限须提供定量限")
        return self


class ResultInput(ResultFields):
    sample_id: str = Field(min_length=1, max_length=36)


class ResultUpdate(Input):
    version: int = Field(ge=1)
    fields: ResultFields


class Review(Input):
    version: int = Field(ge=1)
    action: Literal["CONFIRM", "RETURN"]
    note: str = Field(min_length=1, max_length=1000)


class Search(Input):
    keyword: str = Field(default="", max_length=100)
    site_id: str = Field(default="", max_length=36)
    state: Literal["DRAFT", "RETURNED", "REVIEWED"] | None = None
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=20, ge=1, le=100)


class Trend(Input):
    site_id: str = Field(min_length=1, max_length=36)
    analyte: str = Field(min_length=1, max_length=120)
    laboratory: str = Field(min_length=1, max_length=200)
    analysis_method: str = Field(min_length=1, max_length=200)
    sampling_method: Literal["GRAB", "COMPOSITE"]
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def bounded_range(self):
        if not 0 <= (self.end_date - self.start_date).days <= 366:
            raise ValueError("查询日期必须顺序正确且跨度不超过366天")
        return self


def site_json(row):
    return {name: getattr(row, name) for name in ("id", "code", "name", "district", "plant_name", "catchment", "active", "state_note", "version")}


def sample_json(row, site_name):
    return {"id": row.id, "code": row.code, "site_id": row.site_id, "site_name": site_name,
            "sampled_at": row.sampled_at, "sampling_method": row.sampling_method, "collector": row.collector,
            "flow_m3_day": str(row.flow_m3_day) if row.flow_m3_day is not None else None, "quality": row.quality, "note": row.note}


def result_json(row):
    return {"id": row.id, "sample_id": row.sample_id, "unit": "ng/L", "version": row.version,
            "created_by": row.created_by, "state": row.state, "review_note": row.review_note,
            **{name: (str(getattr(row, name)) if getattr(row, name) is not None else None)
               for name in ResultFields.model_fields}}


def create_router(error, audit, reserve, finish, page_result, request_id):
    router = APIRouter(prefix="/api/wastewater", tags=["污水监测（开发验证）"])

    def visible(db, model, user, identity):
        row = db.scalar(select(model).where(model.id == identity, model.org_id == user.org_id))
        if row is None:
            raise error(404, "NOT_FOUND", "记录不存在或无权访问")
        return row

    def event(db, user, row, action, note):
        db.add(Event(org_id=user.org_id, result_id=row.id, actor_id=user.id, action=action, note=note,
                     snapshot=json.dumps(result_json(row), ensure_ascii=False)))

    def paged(db, stmt, data, render, request):
        total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        rows = db.execute(stmt.offset((data.page - 1) * data.page_size).limit(data.page_size)).all()
        return page_result([render(*row) for row in rows], data.page, data.page_size, total, request_id(request))

    @router.post("/sites/search")
    def sites(data: Search, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
        stmt = select(Site).where(Site.org_id == user.org_id)
        if data.keyword:
            stmt = stmt.where(or_(*(column.contains(data.keyword, autoescape=True) for column in (Site.code, Site.name, Site.district))))
        result = paged(db, stmt.order_by(Site.created_at.desc(), Site.id.desc()), data, site_json, request)
        audit(db, user, "WASTEWATER_SITE_LIST", user.org_id); db.commit()
        return result

    @router.post("/sites", status_code=201)
    def create_site(data: SiteInput, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
        record, replay = reserve(db, user, "WASTEWATER_SITE_CREATE", key, data.model_dump())
        if replay: return replay
        row = Site(org_id=user.org_id, created_by=user.id, **data.model_dump()); db.add(row)
        try: db.flush()
        except IntegrityError:
            db.rollback(); raise error(409, "DUPLICATE_CODE", "本组织已存在此采样点编号")
        result = site_json(row); audit(db, user, "WASTEWATER_SITE_CREATE", row.id)
        finish(record, result, 201, row.id); db.commit(); return result

    @router.post("/sites/{identity}/state")
    def site_state(identity: str, data: SiteState, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
        visible(db, Site, user, identity)
        record, replay = reserve(db, user, "WASTEWATER_SITE_STATE", key, {"id": identity, **data.model_dump()})
        if replay: return replay
        changed = db.execute(update(Site).where(Site.id == identity, Site.org_id == user.org_id, Site.version == data.version).values(active=data.active, state_note=data.reason, version=Site.version + 1))
        if changed.rowcount != 1: raise error(409, "VERSION_CONFLICT", "点位已变化，请重新查询")
        result = {"id": identity, "active": data.active, "version": data.version + 1}
        audit(db, user, "WASTEWATER_SITE_ENABLE" if data.active else "WASTEWATER_SITE_DISABLE", identity)
        finish(record, result, 200, identity); db.commit(); return result

    @router.post("/samples/search")
    def samples(data: Search, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
        stmt = select(Sample, Site.name).join(Site, Sample.site_id == Site.id).where(Sample.org_id == user.org_id, Site.org_id == user.org_id)
        if data.site_id: stmt = stmt.where(Sample.site_id == data.site_id)
        if data.keyword: stmt = stmt.where(Sample.code.contains(data.keyword, autoescape=True))
        result = paged(db, stmt.order_by(Sample.sampled_at.desc(), Sample.id.desc()), data, sample_json, request)
        audit(db, user, "WASTEWATER_SAMPLE_LIST", user.org_id); db.commit(); return result

    @router.post("/samples", status_code=201)
    def create_sample(data: SampleInput, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
        site = visible(db, Site, user, data.site_id)
        record, replay = reserve(db, user, "WASTEWATER_SAMPLE_CREATE", key, data.model_dump(mode="json"))
        if replay: return replay
        # Lock the point's version even when no value changes, serializing a
        # concurrent disable against accepting a new sample.
        locked = db.execute(update(Site).where(Site.id == site.id, Site.org_id == user.org_id, Site.active.is_(True)).values(version=Site.version + 1))
        if locked.rowcount != 1: raise error(409, "SITE_INACTIVE", "点位已停用，不能登记新样本")
        row = Sample(org_id=user.org_id, created_by=user.id, **data.model_dump()); db.add(row)
        try: db.flush()
        except IntegrityError:
            db.rollback(); raise error(409, "DUPLICATE_CODE", "本组织已存在此样本编号")
        result = sample_json(row, site.name); audit(db, user, "WASTEWATER_SAMPLE_CREATE", row.id)
        finish(record, result, 201, row.id); db.commit(); return result

    def result_statement(user):
        return select(Result, Sample.code, Sample.sampled_at, Site.name, User.username).join(Sample, Result.sample_id == Sample.id).join(Site, Sample.site_id == Site.id).join(User, Result.created_by == User.id).where(Result.org_id == user.org_id, Sample.org_id == user.org_id, Site.org_id == user.org_id)

    def listed(row, code, sampled_at, name, author):
        return {**result_json(row), "sample_code": code, "sampled_at": sampled_at, "site_name": name, "author": author}

    @router.post("/results/search")
    def results(data: Search, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
        stmt = result_statement(user)
        if data.site_id: stmt = stmt.where(Sample.site_id == data.site_id)
        if data.state: stmt = stmt.where(Result.state == data.state)
        if data.keyword: stmt = stmt.where(or_(Sample.code.contains(data.keyword, autoescape=True), Result.analyte.contains(data.keyword, autoescape=True), Result.report_number.contains(data.keyword, autoescape=True)))
        result = paged(db, stmt.order_by(Result.created_at.desc(), Result.id.desc()), data, listed, request)
        result["current_user_id"] = user.id
        audit(db, user, "WASTEWATER_RESULT_LIST", user.org_id); db.commit(); return result

    @router.post("/results", status_code=201)
    def create_result(data: ResultInput, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
        visible(db, Sample, user, data.sample_id)
        record, replay = reserve(db, user, "WASTEWATER_RESULT_CREATE", key, data.model_dump(mode="json"))
        if replay: return replay
        row = Result(org_id=user.org_id, created_by=user.id, **data.model_dump()); db.add(row)
        try: db.flush()
        except IntegrityError:
            db.rollback(); raise error(409, "DUPLICATE_RESULT", "该样本、指标、实验室和报告编号已有记录，请修改原草稿或核对报告版本")
        result = result_json(row); event(db, user, row, "CREATE", "录入检测结果草稿")
        audit(db, user, "WASTEWATER_RESULT_CREATE", row.id); finish(record, result, 201, row.id); db.commit(); return result

    @router.post("/results/{identity}/update")
    def update_result(identity: str, data: ResultUpdate, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
        row = visible(db, Result, user, identity)
        if row.created_by != user.id: raise error(403, "FORBIDDEN", "仅录入人可修改未复核结果")
        record, replay = reserve(db, user, "WASTEWATER_RESULT_UPDATE", key, {"id": identity, **data.model_dump(mode="json")})
        if replay: return replay
        try:
            changed = db.execute(update(Result).where(Result.id == identity, Result.org_id == user.org_id, Result.version == data.version, Result.state.in_(("DRAFT", "RETURNED"))).values(**data.fields.model_dump(), state="DRAFT", version=Result.version + 1))
        except IntegrityError:
            db.rollback(); raise error(409, "DUPLICATE_RESULT", "该样本、指标、实验室和报告编号已有其他结果")
        if changed.rowcount != 1: raise error(409, "VERSION_OR_STATE_CONFLICT", "结果已变化或已复核，请重新查询")
        db.refresh(row); result = result_json(row); event(db, user, row, "UPDATE", "修订未复核结果")
        audit(db, user, "WASTEWATER_RESULT_UPDATE", identity); finish(record, result, 200, identity); db.commit(); return result

    @router.post("/results/{identity}/review")
    def review_result(identity: str, data: Review, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
        row = visible(db, Result, user, identity)
        if row.created_by == user.id: raise error(403, "FORBIDDEN", "须由录入人以外的本组织账号核对")
        record, replay = reserve(db, user, "WASTEWATER_RESULT_REVIEW", key, {"id": identity, **data.model_dump()})
        if replay: return replay
        target = "REVIEWED" if data.action == "CONFIRM" else "RETURNED"
        changed = db.execute(update(Result).where(Result.id == identity, Result.org_id == user.org_id, Result.version == data.version, Result.state == "DRAFT").values(state=target, reviewed_by=user.id, review_note=data.note, version=Result.version + 1))
        if changed.rowcount != 1: raise error(409, "VERSION_OR_STATE_CONFLICT", "结果已变化或不在待复核状态")
        db.refresh(row); result = result_json(row); event(db, user, row, data.action, data.note)
        audit(db, user, "WASTEWATER_RESULT_REVIEW", identity); finish(record, result, 200, identity); db.commit(); return result

    @router.get("/results/{identity}/events")
    def events(identity: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        visible(db, Result, user, identity)
        rows = db.execute(select(Event, User.username).join(User, Event.actor_id == User.id).where(Event.result_id == identity, Event.org_id == user.org_id).order_by(Event.created_at.desc(), Event.id.desc()).limit(20)).all()
        audit(db, user, "WASTEWATER_RESULT_HISTORY", identity); db.commit()
        return {"items": [{"id": event.id, "action": event.action, "actor": name, "note": event.note, "created_at": event.created_at, "snapshot": json.loads(event.snapshot)} for event, name in rows]}

    @router.post("/trends/search")
    def trends(data: Trend, user: User = Depends(current_user), db: Session = Depends(get_db)):
        site = visible(db, Site, user, data.site_id)
        zone = timezone(timedelta(hours=8))
        start = datetime.combine(data.start_date, time.min, zone)
        end = datetime.combine(data.end_date + timedelta(days=1), time.min, zone)
        ranked = select(Result.id, Result.sample_id, Result.concentration, Result.quantification_limit, Result.detection, Sample.code, Sample.sampled_at,
                        func.row_number().over(partition_by=Result.sample_id, order_by=(Result.created_at.desc(), Result.id.desc())).label("position")).join(Sample, Result.sample_id == Sample.id).where(
                            Result.org_id == user.org_id, Sample.org_id == user.org_id, Sample.site_id == site.id,
                            Result.analyte == data.analyte, Result.laboratory == data.laboratory, Result.analysis_method == data.analysis_method,
                            Result.state == "REVIEWED", Sample.quality == "VALID", Sample.sampling_method == data.sampling_method,
                            Sample.sampled_at >= start, Sample.sampled_at < end).subquery()
        rows = db.execute(select(ranked).where(ranked.c.position == 1).order_by(ranked.c.sampled_at.asc(), ranked.c.id.asc()).limit(1001)).mappings().all()
        if len(rows) > 1000: raise error(422, "TREND_TOO_LARGE", "结果超过1000个样本，请缩小日期范围")
        points = [{"result_id": row["id"], "sample_code": row["code"], "sampled_at": row["sampled_at"], "detection": row["detection"],
                   "concentration": str(row["concentration"]) if row["concentration"] is not None else None,
                   "quantification_limit": str(row["quantification_limit"]) if row["quantification_limit"] is not None else None} for row in rows]
        audit(db, user, "WASTEWATER_TREND_VIEW", site.id); db.commit()
        return {"site_name": site.name, "unit": "ng/L", "points": points, "sample_count": len(points),
                "quantified_count": sum(point["detection"] == "QUANTIFIED" for point in points),
                "basis": "同点位、指标、实验室、检测方法和采样方式；仅质量正常、已复核结果；每个样本按录入时间取本口径最近一条已复核记录。未检出及低于定量限不按零值绘图。"}

    return router
