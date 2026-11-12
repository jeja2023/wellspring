"""Actionable work queues. Business totals belong to the separate data screen."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import Date, JSON, String, case, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from .access_policy import effective_permissions
from .db import get_db
from .intelligence_models import ClueDelivery
from .models import Case, Clue, InvestigationTask, PersonDraft, User
from .person_core import WRITE_PERMISSIONS, person_scope
from .person_models import PersonRecord, PersonTask, PersonTransfer
from .place_models import Place, PlaceIncident, PlaceInspection
from .security import current_user
from .wastewater_models import WastewaterResult, WastewaterSample, WastewaterSite

BEIJING = timezone(timedelta(hours=8))
MODULES = {'intelligence': '情报线索', 'persons': '人员档案', 'places': '重点场所', 'wastewater': '污水监测'}


def task_sources(db, user):
    permissions = effective_permissions(db, user)
    sources, modules = [], []

    def allowed(*codes):
        return set(codes) <= permissions

    delivery_title = (cast(ClueDelivery.snapshot_json, JSON)['title'].as_string()
                      if db.get_bind().dialect.name == 'postgresql'
                      else func.json_extract(ClueDelivery.snapshot_json, '$.title'))

    def add(module, kind, queue, model, resource_id, title, *, due=None, tab='', keyword=None,
            scope='unit', filters=(), joins=()):
        statement = select(
            literal(module).label('module'), literal(kind).label('kind'), literal(queue).label('queue'),
            model.id.label('id'), resource_id.label('resource_id'), title.label('title'),
            model.status.label('status') if hasattr(model, 'status') else model.verification_status.label('status') if model is PersonDraft or model is PersonRecord else model.state.label('status'),
            (due if due is not None else cast(literal(None), Date)).label('due_date'),
            model.created_at.label('created_at'), literal(tab).label('tab'),
            (keyword if keyword is not None else cast(literal(None), String)).label('keyword'),
            (literal(scope) if isinstance(scope, str) else scope).label('scope'),
        ).select_from(model)
        for target, condition in joins:
            statement = statement.join(target, condition)
        sources.append(statement.where(*filters))
        if module not in modules:
            modules.append(module)

    if allowed('intelligence.read', 'intelligence.write'):
        common = [InvestigationTask.org_id == user.org_id, Clue.org_id == user.org_id]
        for queue, filters in [
            ('todo', [InvestigationTask.assignee_id == user.id, InvestigationTask.status.in_(['OPEN', 'RETURNED'])]),
            ('review', [InvestigationTask.status == 'PENDING_REVIEW', InvestigationTask.last_submitter_id.is_not(None),
                        InvestigationTask.last_submitter_id != user.id]),
        ]:
            add('intelligence', 'investigation', queue, InvestigationTask, Clue.id, Clue.title,
                due=InvestigationTask.due_date, scope='mine' if queue == 'todo' else 'unit',
                filters=[*common, *filters], joins=[(Clue, Clue.id == InvestigationTask.clue_id)])
    if allowed('intelligence.read', 'intelligence.dispose'):
        add('intelligence', 'delivery', 'todo', ClueDelivery, ClueDelivery.id, delivery_title,
            due=ClueDelivery.due_date, tab='received',
            scope=case((ClueDelivery.assignee_id == user.id, 'mine'), else_='claim'),
            filters=[ClueDelivery.recipient_org_id == user.org_id,
                     or_((ClueDelivery.status == 'OPEN') & ClueDelivery.assignee_id.is_(None),
                         ClueDelivery.status.in_(['PROCESSING', 'RETURNED']) & (ClueDelivery.assignee_id == user.id))],
            joins=[])
    if allowed('intelligence.read', 'intelligence.review'):
        add('intelligence', 'delivery', 'review', ClueDelivery, ClueDelivery.id, delivery_title,
            due=ClueDelivery.due_date, tab='sent',
            filters=[ClueDelivery.sender_org_id == user.org_id, ClueDelivery.status == 'PENDING_REVIEW',
                     ClueDelivery.assignee_id.is_not(None), ClueDelivery.assignee_id != user.id],
            joins=[])
    if allowed('persons.read', 'persons.health', 'persons.followup'):
        add('persons', 'person-task', 'todo', PersonTask, PersonDraft.id, PersonDraft.name + ' · ' + PersonTask.title,
            due=PersonTask.due_on, tab='TASKS',
            scope=case((PersonDraft.responsible_user_id == user.id, 'mine'), else_='unit'),
            filters=[PersonTask.org_id == user.org_id, PersonTask.status == 'OPEN', person_scope(user)],
            joins=[(PersonDraft, PersonDraft.id == PersonTask.person_id)])
    if allowed('persons.read', 'persons.verify', 'persons.identity'):
        add('persons', 'person-identity', 'review', PersonDraft, PersonDraft.id, PersonDraft.name,
            tab='BASE', filters=[func.coalesce(PersonDraft.responsible_org_id, PersonDraft.org_id) == user.org_id,
                                 PersonDraft.verification_status == 'UNVERIFIED',
                                 func.coalesce(PersonDraft.updated_by, PersonDraft.created_by) != user.id,
                                 PersonDraft.document_number.is_not(None), PersonDraft.document_number != ''])
    for kind, permission in WRITE_PERMISSIONS.items():
        if not allowed('persons.read', permission, 'cases.read' if kind == 'CASE' else 'persons.health'):
            continue
        joins = [(PersonDraft, PersonDraft.id == PersonRecord.person_id)]
        common = [PersonRecord.kind == kind, PersonRecord.manager_org_id == user.org_id, person_scope(user)]
        if kind == 'CASE':
            joins.append((Case, Case.id == PersonRecord.case_id))
            common.append(Case.org_id == user.org_id)
        if kind in {'CASE', 'MEASURE'}:
            common.append(PersonDraft.verification_status == 'VERIFIED')
        add('persons', 'person-record', 'todo', PersonRecord, PersonDraft.id, PersonDraft.name,
            tab=kind, scope='mine', filters=[*common, PersonRecord.verification_status == 'RETURNED',
                                            func.coalesce(PersonRecord.updated_by, PersonRecord.created_by) == user.id], joins=joins)
        if allowed('persons.verify'):
            add('persons', 'person-record', 'review', PersonRecord, PersonDraft.id, PersonDraft.name,
                tab=kind, filters=[*common, PersonRecord.verification_status == 'PENDING',
                                   func.coalesce(PersonRecord.updated_by, PersonRecord.created_by) != user.id], joins=joins)
    if allowed('persons.read', 'persons.transfer'):
        add('persons', 'person-transfer', 'review', PersonTransfer, PersonDraft.id, PersonDraft.name,
            tab='TRANSFERS', filters=[PersonTransfer.target_org_id == user.org_id, PersonTransfer.status == 'PENDING'],
            joins=[(PersonDraft, PersonDraft.id == PersonTransfer.person_id)])
    if allowed('places.read', 'places.write'):
        add('places', 'inspection', 'todo', PlaceInspection, Place.id, Place.name,
            due=PlaceInspection.due_on, tab='inspections',
            filters=[PlaceInspection.org_id == user.org_id, Place.org_id == user.org_id, PlaceInspection.status == 'OPEN'],
            joins=[(Place, Place.id == PlaceInspection.place_id)])
        add('places', 'incident', 'todo', PlaceIncident, Place.id, PlaceIncident.title, tab='incidents',
            filters=[PlaceIncident.org_id == user.org_id, Place.org_id == user.org_id,
                     or_(PlaceIncident.status == 'OPEN', (PlaceIncident.status.in_(['DRAFT', 'RETURNED'])) & (PlaceIncident.last_editor_id == user.id))],
            joins=[(Place, Place.id == PlaceIncident.place_id)])
    if allowed('places.read', 'places.review'):
        add('places', 'incident', 'review', PlaceIncident, Place.id, PlaceIncident.title, tab='incidents',
            filters=[PlaceIncident.org_id == user.org_id, Place.org_id == user.org_id,
                     or_((PlaceIncident.status == 'DRAFT') & (PlaceIncident.last_editor_id != user.id),
                         (PlaceIncident.status == 'SUBMITTED') & PlaceIncident.submitted_by.is_not(None) & (PlaceIncident.submitted_by != user.id))],
            joins=[(Place, Place.id == PlaceIncident.place_id)])
    if allowed('wastewater.read', 'wastewater.write'):
        joins = [(WastewaterSample, WastewaterSample.id == WastewaterResult.sample_id),
                 (WastewaterSite, WastewaterSite.id == WastewaterSample.site_id)]
        common = [WastewaterResult.org_id == user.org_id, WastewaterSample.org_id == user.org_id, WastewaterSite.org_id == user.org_id]
        for queue, filters in [('todo', [WastewaterResult.state == 'RETURNED', WastewaterResult.created_by == user.id]),
                               ('review', [WastewaterResult.state == 'DRAFT', WastewaterResult.created_by != user.id])]:
            add('wastewater', 'water-result', queue, WastewaterResult, WastewaterResult.id,
                WastewaterSample.code + ' · ' + WastewaterResult.analyte, tab='results', keyword=WastewaterResult.report_number,
                scope='mine' if queue == 'todo' else 'unit', filters=[*common, *filters], joins=joins)
    return sources, modules


def overview(db, user, *, queue='todo', module='all', page=1, page_size=10, instant=None):
    instant = instant or datetime.now(timezone.utc)
    today = instant.astimezone(BEIJING).date()
    sources, modules = task_sources(db, user)
    counts = dict(todo=0, review=0, overdue=0, due_today=0)
    items = []
    if sources:
        tasks = union_all(*sources).subquery()
        filters = [] if module == 'all' else [tasks.c.module == module]
        conditions = {'todo': tasks.c.queue == 'todo', 'review': tasks.c.queue == 'review',
                      'overdue': tasks.c.due_date < today, 'due_today': tasks.c.due_date == today}
        counts = dict(db.execute(select(*(func.count().filter(condition).label(name) for name, condition in conditions.items()))
                                 .select_from(tasks).where(*filters)).mappings().one())
        total = counts[queue]
        page = min(page, max(1, (total + page_size - 1) // page_size))
        rows = db.execute(select(tasks).where(*filters, conditions[queue]).order_by(
            tasks.c.due_date.is_(None), tasks.c.due_date, tasks.c.created_at, tasks.c.kind, tasks.c.id
        ).offset((page - 1) * page_size).limit(page_size)).mappings().all()
        for row in rows:
            item = dict(row)
            due = item['due_date']
            item['overdue_days'] = max(0, (today - due).days) if due else 0
            item['due_today'] = due == today
            items.append(item)
    else:
        page = 1
    return dict(items=items, total=counts[queue], page=page, page_size=page_size,
                has_more=page * page_size < counts[queue], counts=counts, queue=queue, module=module,
                available_modules=[{'key': key, 'name': MODULES[key]} for key in modules],
                generated_at=instant, today=today, timezone='Asia/Shanghai')


def create_router(audit):
    router = APIRouter(prefix='/api/workbench', tags=['工作台办理事项'])

    @router.get('/tasks')
    def tasks(request: Request, queue: Literal['todo', 'review', 'overdue', 'due_today'] = 'todo',
              module: Literal['all', 'intelligence', 'persons', 'places', 'wastewater'] = 'all',
              page: int = Query(1, ge=1, le=100000), page_size: int = Query(10, ge=1, le=50),
              user: User = Depends(current_user), db: Session = Depends(get_db)):
        result = overview(db, user, queue=queue, module=module, page=page, page_size=page_size)
        result['request_id'] = request.state.request_id
        audit(db, user, 'WORKBENCH_VIEW', user.id)
        db.commit()
        return result

    return router
