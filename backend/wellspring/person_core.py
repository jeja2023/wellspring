"""Shared person scope, redaction and record-derived overview."""
from datetime import timedelta,timezone
import json
from sqlalchemy import exists,func,or_,select
from .access_policy import effective_permissions
from .models import Case,Organization,PersonDraft,User,now
from .person_models import PersonEvent,PersonRecord,PersonTask,PersonTransfer

WRITE_PERMISSIONS={'USE':'persons.use','CASE':'persons.cases','MEASURE':'persons.treatment','TEST':'persons.followup','FOLLOWUP':'persons.followup'}
SENSITIVE_PERMISSIONS={'persons.identity','persons.health','persons.verify','persons.use','persons.cases','persons.treatment','persons.followup','persons.transfer'}


def today():return now().astimezone(timezone(timedelta(hours=8))).date()


def current_org(person):return person.responsible_org_id or person.org_id


def person_scope(user):return or_(PersonDraft.org_id==user.org_id,PersonDraft.responsible_org_id==user.org_id,
    exists(select(PersonTransfer.id).where(PersonTransfer.person_id==PersonDraft.id,PersonTransfer.status=='ACCEPTED',or_(PersonTransfer.source_org_id==user.org_id,PersonTransfer.target_org_id==user.org_id))))


def visible_person(db,user,identity,error,write=False):
    row=db.scalar(select(PersonDraft).where(PersonDraft.id==identity,person_scope(user)))
    if not row:raise error(404,'NOT_FOUND','人员不存在或无权访问')
    if write and current_org(row)!=user.org_id:raise error(403,'FORBIDDEN','仅当前责任单位可以办理人员主档和新增业务')
    return row


def record_scope(user):return or_(PersonRecord.org_id==user.org_id,PersonRecord.manager_org_id==user.org_id)


def readable_kinds(db,user):
    permissions=effective_permissions(db,user)
    return (['USE','MEASURE','TEST','FOLLOWUP'] if 'persons.health' in permissions else [])+(['CASE'] if 'cases.read' in permissions else [])


def record_filters(db,user,person_id):
    return [PersonRecord.person_id==person_id,record_scope(user),PersonRecord.kind.in_(readable_kinds(db,user)),
        or_(PersonRecord.kind!='CASE',exists(select(Case.id).where(Case.id==PersonRecord.case_id,Case.org_id==user.org_id)))]


def visible_record(db,user,identity,error):
    row=db.get(PersonRecord,identity)
    if not row:raise error(404,'NOT_FOUND','业务记录不存在或无权访问')
    visible_person(db,user,row.person_id,error)
    if not db.scalar(select(PersonRecord.id).where(PersonRecord.id==identity,*record_filters(db,user,row.person_id))):raise error(404,'NOT_FOUND','业务记录不存在或无权访问')
    return row


def mask(value):
    return '—' if not value else ('*'*max(4,len(value)-4)+value[-4:])


def profile_json(db,user,row,detail=False):
    permissions=effective_permissions(db,user);organization=db.get(Organization,current_org(row));handler=db.get(User,row.responsible_user_id) if row.responsible_user_id else None
    result={name:getattr(row,name) for name in ['id','name','source','verification_status','version','created_at','verified_at','document_type']}
    result.update(document_mask=mask(row.document_number),responsible_org_id=current_org(row),responsible_org=organization.name if organization else '',responsible_user_id=row.responsible_user_id,responsible_user=handler.username if handler else None,can_manage=current_org(row)==user.org_id,legacy_candidates_visible=row.org_id==user.org_id)
    counts=dict(db.execute(select(PersonRecord.kind,func.count()).where(*record_filters(db,user,row.id),PersonRecord.verification_status=='VERIFIED').group_by(PersonRecord.kind)).all())
    measures=db.scalars(select(PersonRecord).where(*record_filters(db,user,row.id),PersonRecord.kind=='MEASURE',PersonRecord.verification_status=='VERIFIED',PersonRecord.state.in_(['DECIDED','ACTIVE'])).order_by(PersonRecord.occurred_on.desc(),PersonRecord.id)).all() if 'persons.health' in permissions else []
    result.update(case_count=counts.get('CASE',0) if 'cases.read' in permissions else None,use_count=counts.get('USE',0) if 'persons.health' in permissions else None,
        current_measures=[{'id':r.id,'record_type':r.record_type,'state':r.state,'expected_end_on':r.expected_end_on,'needs_end_check':bool(r.expected_end_on and r.expected_end_on<=today())} for r in measures],health_visible='persons.health' in permissions,measure_conflict=len(measures)>1,
        task_count=int(db.scalar(select(func.count()).select_from(PersonTask).where(PersonTask.person_id==row.id,PersonTask.org_id==user.org_id,PersonTask.status=='OPEN')) or 0) if 'persons.health' in permissions else None)
    if detail:
        result.update(created_by=row.created_by,identity_visible='persons.identity' in permissions,verified_by=row.verified_by)
        if 'persons.identity' in permissions:result.update(document_number=row.document_number,birth_date=row.birth_date,phone=row.phone,address=row.address)
    return result


def record_json(db,row):
    result={name:getattr(row,name) for name in ['id','person_id','org_id','manager_org_id','kind','record_type','occurred_on','source','document_no','basis','case_id','replaces_id','verification_status','state','expected_end_on','actual_start_on','actual_end_on','created_by','updated_by','verified_by','verified_at','version','created_at']}
    result['details']=json.loads(row.details_json)
    if row.case_id:
        case=db.get(Case,row.case_id);result['case_number']=case.number if case else None;result['case_title']=case.title if case else None
    return result


def add_event(db,user,person,action,note,record=None,payload=None):
    db.add(PersonEvent(person_id=person.id,record_id=record.id if record else None,org_id=user.org_id,actor_id=user.id,action=action,note=note,payload_json=json.dumps(payload,ensure_ascii=False,default=str) if payload else None))
