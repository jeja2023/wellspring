"""Organization-scoped place registers, inspections and independently reviewed incidents."""
from datetime import date, datetime, timedelta, timezone
import json
from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .access_policy import effective_permissions
from .clue_deliveries import lock_flow
from .db import get_db
from .models import Clue, IntelligenceEvent, User, now
from .place_models import Place, PlaceEvent, PlaceIncident, PlaceInspection
from .security import current_user


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class PlaceFields(Input):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    kind: Literal['APARTMENT', 'BAR', 'ENTERTAINMENT', 'STREET', 'OTHER']
    district: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)
    responsible: str = Field(min_length=1, max_length=100)
    management_basis: str = Field(min_length=1, max_length=2000)
    review_on: date | None = None


class PlaceEdit(PlaceFields):
    version: int = Field(ge=1)


class Search(Input):
    keyword: str = Field(default='', max_length=100)
    kind: Literal['APARTMENT', 'BAR', 'ENTERTAINMENT', 'STREET', 'OTHER'] | None = None
    active: bool | None = None
    page: int = Field(default=1, ge=1, le=100000)


class Action(Input):
    version: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=2000)


class PlaceState(Action):
    active: bool


class InspectionInput(Input):
    inspected_on: date
    findings: str = Field(min_length=1, max_length=5000)
    due_on: date | None = None
    requires_action: bool = False

    @model_validator(mode='after')
    def dates(self):
        if self.inspected_on > (now() + timedelta(hours=8)).date():
            raise ValueError('巡查日期不能晚于今天')
        if self.requires_action and (not self.due_on or self.due_on < self.inspected_on):
            raise ValueError('需要整改时须填写不早于巡查日期的期限')
        if not self.requires_action and self.due_on:
            raise ValueError('无需整改时不填写整改期限')
        return self


class IncidentInput(Input):
    title: str = Field(min_length=1, max_length=200)
    occurred_at: datetime
    source: str = Field(min_length=1, max_length=200)
    facts: str = Field(min_length=1, max_length=5000)
    material_ref: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def instant(self):
        if self.occurred_at.tzinfo is None or self.occurred_at > now():
            raise ValueError('事件时间须带时区且不晚于现在')
        self.occurred_at = self.occurred_at.astimezone(timezone.utc)
        return self


class IncidentEdit(IncidentInput):
    version: int = Field(ge=1)


class IncidentAction(Action):
    action: Literal['CONFIRM', 'RETURN', 'SUBMIT', 'CLOSE', 'REOPEN']


def row_json(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns if column.name != 'org_id'}


def create_router(error, audit, reserve, finish, page_result, request_id):
    router = APIRouter(prefix='/api/places', tags=['重点场所'])

    def visible(db, user, model, identity):
        row = db.scalar(select(model).where(model.id == identity, model.org_id == user.org_id))
        if not row:
            raise error(404, 'NOT_FOUND', '记录不存在或无权访问')
        return row

    def check_version(row, version):
        if row.version != version:
            raise error(409, 'VERSION_CONFLICT', '记录已变化，请刷新后重试')

    def event(db, user, row, action, note):
        db.add(PlaceEvent(org_id=user.org_id, place_id=row.id if isinstance(row, Place) else row.place_id,
            resource_id=row.id, actor_id=user.id, action=action, note=note,
            snapshot_json=json.dumps(jsonable_encoder(row_json(row)), ensure_ascii=False)))
        audit(db, user, 'PLACE_' + action, row.id)

    def saved(db, user, row, record, action, note, status=200):
        db.flush()
        event(db, user, row, action, note)
        result = row_json(row)
        finish(record, result, status, row.id)
        db.commit()
        return result

    @router.post('/search')
    def search(data: Search, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
        filters = [Place.org_id == user.org_id]
        if data.keyword:
            filters.append(Place.name.contains(data.keyword, autoescape=True) | Place.code.contains(data.keyword, autoescape=True) | Place.address.contains(data.keyword, autoescape=True))
        if data.kind:
            filters.append(Place.kind == data.kind)
        if data.active is not None:
            filters.append(Place.active == data.active)
        total = db.scalar(select(func.count()).select_from(Place).where(*filters)) or 0
        rows = db.scalars(select(Place).where(*filters).order_by(Place.updated_at.desc(), Place.id.desc()).offset((data.page-1)*20).limit(20)).all()
        audit(db, user, 'PLACE_SEARCH', user.org_id); db.commit()
        return page_result([row_json(row) for row in rows], data.page, 20, total, request_id(request))

    @router.post('', status_code=201)
    def create(data: PlaceFields, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        lock_flow(db, user, 'places.write', error, 'places.read')
        record, replay = reserve(db, user, 'PLACE_CREATE', key, data.model_dump())
        if replay:
            return replay
        row = Place(**data.model_dump(), org_id=user.org_id, created_by=user.id)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback(); raise error(409, 'CODE_EXISTS', '本组织已有相同场所编号') from None
        return saved(db, user, row, record, 'CREATED', '建立场所台账', 201)

    @router.get('/{identity}')
    def detail(identity: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = visible(db, user, Place, identity)
        result = row_json(row)
        result['open_inspections'] = db.scalar(select(func.count()).select_from(PlaceInspection).where(PlaceInspection.place_id == identity, PlaceInspection.status == 'OPEN')) or 0
        result['open_incidents'] = db.scalar(select(func.count()).select_from(PlaceIncident).where(PlaceIncident.place_id == identity, PlaceIncident.status != 'CLOSED')) or 0
        audit(db, user, 'PLACE_DETAIL', identity); db.commit()
        return result

    @router.post('/{identity}/update')
    def edit(identity: str, data: PlaceEdit, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        lock_flow(db, user, 'places.write', error, 'places.read'); row = visible(db, user, Place, identity)
        record, replay = reserve(db, user, 'PLACE_EDIT', key, {'id': identity, **data.model_dump()})
        if replay: return replay
        check_version(row, data.version)
        for name, value in data.model_dump(exclude={'version'}).items(): setattr(row, name, value)
        row.version += 1; row.updated_at = now()
        try: db.flush()
        except IntegrityError:
            db.rollback(); raise error(409, 'CODE_EXISTS', '本组织已有相同场所编号') from None
        return saved(db, user, row, record, 'UPDATED', '更正场所资料')

    @router.post('/{identity}/state')
    def state(identity: str, data: PlaceState, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        lock_flow(db, user, 'places.write', error, 'places.read'); row = visible(db, user, Place, identity)
        record, replay = reserve(db, user, 'PLACE_STATE', key, {'id': identity, **data.model_dump()})
        if replay: return replay
        check_version(row, data.version)
        row.active = data.active; row.version += 1; row.updated_at = now()
        return saved(db, user, row, record, 'STATE_CHANGED', data.note)

    @router.get('/{identity}/{area}')
    def records(identity: str, area: Literal['inspections', 'incidents', 'history'], request: Request, page: int = Query(1, ge=1, le=100000), focus_id: str | None = Query(None,max_length=36), user: User = Depends(current_user), db: Session = Depends(get_db)):
        visible(db, user, Place, identity)
        model = {'inspections': PlaceInspection, 'incidents': PlaceIncident, 'history': PlaceEvent}[area]
        filters = [model.place_id == identity, model.org_id == user.org_id]
        if focus_id: filters.append(model.id == focus_id)
        total = db.scalar(select(func.count()).select_from(model).where(*filters)) or 0
        rows = db.scalars(select(model).where(*filters).order_by(model.created_at.desc(), model.id.desc()).offset((page-1)*20).limit(20)).all()
        items = [row_json(row) for row in rows]
        if area == 'history':
            for item in items:
                item['snapshot'] = json.loads(item.pop('snapshot_json'))
        audit(db, user, 'PLACE_RECORDS_READ', identity); db.commit()
        return page_result(items, page, 20, total, request_id(request))

    @router.post('/{identity}/inspections', status_code=201)
    def inspect(identity: str, data: InspectionInput, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        lock_flow(db, user, 'places.write', error, 'places.read'); place = visible(db, user, Place, identity)
        record, replay = reserve(db, user, 'PLACE_INSPECT', key, {'id': identity, **data.model_dump()})
        if replay: return replay
        if not place.active: raise error(409, 'PLACE_INACTIVE', '已停用场所不再登记新巡查')
        row = PlaceInspection(**data.model_dump(exclude={'requires_action'}), org_id=user.org_id, place_id=identity, created_by=user.id, status='OPEN' if data.requires_action else 'DONE')
        db.add(row)
        return saved(db, user, row, record, 'INSPECTED', '登记巡查及整改要求', 201)

    @router.post('/inspections/{identity}/complete')
    def complete(identity: str, data: Action, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        lock_flow(db, user, 'places.write', error, 'places.read'); row = visible(db, user, PlaceInspection, identity)
        record, replay = reserve(db, user, 'PLACE_INSPECTION_COMPLETE', key, {'id': identity, **data.model_dump()})
        if replay: return replay
        check_version(row, data.version)
        if row.status != 'OPEN': raise error(409, 'INVALID_STATE', '该巡查没有待完成整改')
        row.status = 'DONE'; row.result_note = data.note; row.completed_by = user.id; row.completed_at = now(); row.version += 1
        return saved(db, user, row, record, 'INSPECTION_COMPLETED', data.note)

    @router.post('/{identity}/incidents', status_code=201)
    def incident(identity: str, data: IncidentInput, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        lock_flow(db, user, 'places.write', error, 'places.read'); place = visible(db, user, Place, identity)
        record, replay = reserve(db, user, 'PLACE_INCIDENT_CREATE', key, {'id': identity, **data.model_dump()})
        if replay: return replay
        if not place.active: raise error(409, 'PLACE_INACTIVE', '已停用场所不再登记新事件')
        row = PlaceIncident(**data.model_dump(), org_id=user.org_id, place_id=identity, created_by=user.id, last_editor_id=user.id)
        db.add(row)
        return saved(db, user, row, record, 'INCIDENT_CREATED', '登记待核验事件', 201)

    @router.post('/incidents/{identity}/update')
    def incident_edit(identity: str, data: IncidentEdit, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        lock_flow(db, user, 'places.write', error, 'places.read'); row = visible(db, user, PlaceIncident, identity)
        record, replay = reserve(db, user, 'PLACE_INCIDENT_EDIT', key, {'id': identity, **data.model_dump()})
        if replay: return replay
        check_version(row, data.version)
        if row.status not in {'DRAFT', 'RETURNED'}: raise error(409, 'INVALID_STATE', '仅待核验或退回的事件可补充资料')
        for name, value in data.model_dump(exclude={'version'}).items(): setattr(row, name, value)
        row.status = 'DRAFT'; row.last_editor_id = user.id; row.version += 1
        return saved(db, user, row, record, 'INCIDENT_UPDATED', '补充事件资料并重新送核')

    @router.post('/incidents/{identity}/transition')
    def transition(identity: str, data: IncidentAction, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        permission = 'places.write' if data.action == 'SUBMIT' else 'places.review'
        lock_flow(db, user, permission, error, 'places.read'); row = visible(db, user, PlaceIncident, identity)
        record, replay = reserve(db, user, 'PLACE_INCIDENT_TRANSITION', key, {'id': identity, **data.model_dump()})
        if replay: return replay
        check_version(row, data.version)
        if data.action in {'CONFIRM', 'RETURN'} and row.status in {'DRAFT', 'RETURNED'}:
            if row.last_editor_id == user.id: raise error(403, 'SELF_REVIEW', '不能核验本人登记或修改的事件')
            if row.status == 'RETURNED' and data.action == 'CONFIRM': raise error(409, 'INVALID_STATE', '退回事件须先补充资料重新送核')
            row.status = 'OPEN' if data.action == 'CONFIRM' else 'RETURNED'
        elif data.action == 'SUBMIT' and row.status == 'OPEN':
            row.disposition = data.note; row.submitted_by = user.id; row.status = 'SUBMITTED'
        elif data.action in {'CLOSE', 'RETURN'} and row.status == 'SUBMITTED':
            if not row.submitted_by or row.submitted_by == user.id: raise error(403, 'SELF_REVIEW', '须由另一名有权限人员复核处置反馈')
            row.status = 'CLOSED' if data.action == 'CLOSE' else 'OPEN'
        elif data.action == 'REOPEN' and row.status == 'CLOSED':
            row.status = 'OPEN'
        else: raise error(409, 'INVALID_STATE', '当前事件状态不能执行此操作')
        row.version += 1
        return saved(db, user, row, record, 'INCIDENT_' + data.action, data.note)

    @router.post('/incidents/{identity}/clue')
    def to_clue(identity: str, data: Action, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        lock_flow(db, user, 'places.write', error, 'places.read')
        if not {'intelligence.read', 'intelligence.write'} <= effective_permissions(db, user): raise error(403, 'FORBIDDEN', '当前账号没有线索录入权限')
        row = visible(db, user, PlaceIncident, identity)
        record, replay = reserve(db, user, 'PLACE_INCIDENT_CLUE', key, {'id': identity, **data.model_dump()})
        if replay: return replay
        check_version(row, data.version)
        if row.status not in {'OPEN', 'SUBMITTED', 'CLOSED'}: raise error(409, 'INVALID_STATE', '事件核验后才能显式新建线索')
        if row.clue_id: raise error(409, 'ALREADY_LINKED', '该事件已建立线索记录')
        clue = Clue(org_id=user.org_id, title=row.title, summary=row.facts + '\n资料引用：' + row.material_ref + '\n转录说明：' + data.note,
            source='重点场所事件', reference_no='PLACE-' + row.id, created_by=user.id)
        db.add(clue); db.flush()
        db.add(IntelligenceEvent(org_id=user.org_id, clue_id=clue.id, actor_id=user.id, action='CREATED', after_status='DRAFT', note='来自场所事件 ' + row.id))
        row.clue_id = clue.id; row.version += 1
        audit(db, user, 'CLUE_CREATE', clue.id)
        return saved(db, user, row, record, 'INCIDENT_CLUE_CREATED', data.note)

    return router
