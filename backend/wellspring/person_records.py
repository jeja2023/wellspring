"""Independent records and legal episodes; dates never automatically end measures."""
from datetime import date
import json
from fastapi import APIRouter,Depends,Header,Query,Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func,or_,select,update
from sqlalchemy.orm import Session
from .access_policy import effective_permissions
from .clue_deliveries import lock_flow
from .db import get_db
from .models import Case,PersonDraft,User,now
from .person_core import WRITE_PERMISSIONS,add_event,current_org,readable_kinds,record_filters,record_json,today,visible_person,visible_record
from .person_models import PersonEvent,PersonRecord,PersonTask
from .person_schemas import RecordInput,RecordEdit,Review,Execution,TaskInput,TaskComplete
from .security import current_user


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix='/api/person-drafts',tags=['人员业务记录与措施'])
    def need(db,user,permission):
        if permission not in effective_permissions(db,user):raise error(403,'FORBIDDEN','当前角色没有此项业务办理权限')
    def bump(db,row,version):
        if db.execute(update(PersonDraft).where(PersonDraft.id==row.id,PersonDraft.version==version).values(version=PersonDraft.version+1)).rowcount!=1:raise error(409,'VERSION_CONFLICT','人员档案已变化，请重新查看')
        db.refresh(row)
    def cancel_tasks(db,record):
        db.execute(update(PersonTask).where(PersonTask.record_id==record.id,PersonTask.status=='OPEN').values(status='CANCELLED',result_note='关联记录已撤销、更正或措施已经结束',completed_at=now(),version=PersonTask.version+1))
    def task(db,user,person,record,code,title,due):
        if due:db.add(PersonTask(person_id=person.id,record_id=record.id,org_id=record.manager_org_id,task_type=code,title=title,due_on=due,created_by=user.id))

    @router.get('/{identity}/records')
    def records(identity:str,request:Request,kind:str|None=None,page:int=Query(1,ge=1,le=100000),user:User=Depends(current_user),db:Session=Depends(get_db)):
        visible_person(db,user,identity,error)
        if kind and kind not in readable_kinds(db,user):raise error(403,'FORBIDDEN','当前账号没有此类资料查询权限')
        filters=record_filters(db,user,identity)
        if kind:filters.append(PersonRecord.kind==kind)
        total=db.scalar(select(func.count()).select_from(PersonRecord).where(*filters)) or 0
        rows=db.scalars(select(PersonRecord).where(*filters).order_by(PersonRecord.occurred_on.desc(),PersonRecord.created_at.desc(),PersonRecord.id.desc()).offset((page-1)*20).limit(20)).all()
        result=page_result([record_json(db,row) for row in rows],page,20,total,request_id(request));audit(db,user,'PERSON_RECORDS_VIEW',identity);db.commit();return result

    @router.post('/{identity}/records',status_code=201)
    def create(identity:str,data:RecordInput,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        permission=WRITE_PERMISSIONS[data.kind];lock_flow(db,user,permission,error,'persons.read');person=visible_person(db,user,identity,error,True)
        if data.kind!='CASE':need(db,user,'persons.health')
        else:need(db,user,'cases.read')
        record,replay=reserve(db,user,'PERSON_RECORD_CREATE',key,{'id':person.id,**data.model_dump(mode='json')})
        if replay:return replay
        if data.occurred_on>today():raise error(422,'FUTURE_FACT','事实、决定或检测日期不能晚于今天；计划日期单独填写')
        if data.kind in {'CASE','MEASURE'} and person.verification_status!='VERIFIED':raise error(409,'PERSON_UNVERIFIED','请先完成身份核验，再登记正式案件关系或戒毒措施')
        if data.case_id and not db.scalar(select(Case.id).where(Case.id==data.case_id,Case.org_id==user.org_id)):raise error(404,'NOT_FOUND','案件不存在或无权访问')
        if data.replaces_id:
            previous=visible_record(db,user,data.replaces_id,error)
            if previous.person_id!=person.id or previous.kind!=data.kind or previous.manager_org_id!=user.org_id or previous.verification_status!='VERIFIED':raise error(409,'INVALID_REPLACEMENT','只能更正本单位管理的同人员同类已核验记录')
            if previous.kind=='MEASURE':raise error(409,'MEASURE_EXECUTION_REQUIRED','已核验措施请通过执行、变更或撤销事件处理，不用新记录覆盖执行历史')
        if data.kind=='CASE' and not data.replaces_id and db.scalar(select(PersonRecord.id).where(PersonRecord.person_id==person.id,PersonRecord.case_id==data.case_id,PersonRecord.org_id==user.org_id,PersonRecord.verification_status.in_(['PENDING','VERIFIED']))):raise error(409,'CASE_RELATION_EXISTS','已有该案件的有效或待核验关系，调整角色请使用更正记录')
        bump(db,person,data.person_version)
        row=PersonRecord(person_id=person.id,org_id=user.org_id,manager_org_id=user.org_id,kind=data.kind,record_type=data.record_type,
            occurred_on=data.occurred_on,source=data.source,document_no=data.document_no,basis=data.basis,details_json=json.dumps(data.details,ensure_ascii=False),case_id=data.case_id,replaces_id=data.replaces_id,
            state='DECIDED' if data.kind=='MEASURE' else 'RECORDED',expected_end_on=data.expected_end_on,created_by=user.id,updated_by=user.id)
        db.add(row);db.flush();add_event(db,user,person,'RECORD_CREATED','新增待核验业务记录',row,record_json(db,row))
        audit(db,user,'PERSON_RECORD_CREATE',row.id);result=record_json(db,row);finish(record,result,201,row.id);db.commit();return result

    @router.post('/records/{record_id}/update')
    def edit_record(record_id:str,data:RecordEdit,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,WRITE_PERMISSIONS[data.kind],error,'persons.read');row=visible_record(db,user,record_id,error);person=visible_person(db,user,row.person_id,error,True)
        if row.kind!=data.kind or row.manager_org_id!=user.org_id:raise error(403,'FORBIDDEN','不能更改业务类型或其他责任单位的记录')
        record,replay=reserve(db,user,'PERSON_RECORD_EDIT',key,{'id':row.id,**data.model_dump(mode='json')})
        if replay:return replay
        if data.occurred_on>today():raise error(422,'FUTURE_FACT','事实或决定日期不能晚于今天')
        if data.case_id and not db.scalar(select(Case.id).where(Case.id==data.case_id,Case.org_id==user.org_id)):raise error(404,'NOT_FOUND','关联案件不存在或无权访问')
        if data.replaces_id!=row.replaces_id:raise error(422,'REPLACEMENT_IMMUTABLE','不能通过修改草稿更换更正链')
        before=record_json(db,row);bump(db,person,data.person_version)
        values={name:getattr(data,name) for name in ['record_type','occurred_on','source','document_no','basis','case_id','expected_end_on']}
        values.update(details_json=json.dumps(data.details,ensure_ascii=False),verification_status='PENDING',verified_by=None,verified_at=None,updated_by=user.id,version=PersonRecord.version+1)
        if db.execute(update(PersonRecord).where(PersonRecord.id==row.id,PersonRecord.version==data.version,PersonRecord.verification_status.in_(['PENDING','RETURNED'])).values(**values)).rowcount!=1:raise error(409,'VERSION_OR_STATE_CONFLICT','仅待核验或退回记录可以补充修改，请重新查看')
        db.refresh(row);add_event(db,user,person,'RECORD_UPDATED','补充待核验资料',row,{'before':before,'record':record_json(db,row)})
        audit(db,user,'PERSON_RECORD_EDIT',row.id);result=record_json(db,row);finish(record,result,200,row.id);db.commit();return result

    @router.post('/records/{record_id}/review')
    def review(record_id:str,data:Review,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'persons.verify',error,'persons.read');row=visible_record(db,user,record_id,error);person=visible_person(db,user,row.person_id,error)
        if row.manager_org_id!=user.org_id:raise error(403,'FORBIDDEN','仅当前业务责任单位可以核验或撤销记录')
        need(db,user,WRITE_PERMISSIONS[row.kind])
        record,replay=reserve(db,user,'PERSON_RECORD_REVIEW',key,{'id':row.id,**data.model_dump()})
        if replay:return replay
        if data.action in {'CONFIRM','RETURN'} and (row.updated_by or row.created_by)==user.id:raise error(403,'SELF_REVIEW','登记或最后修改人不能核验自己的业务记录')
        allowed=['PENDING','RETURNED'] if data.action=='CONFIRM' else ['PENDING'] if data.action=='RETURN' else ['PENDING','RETURNED','VERIFIED']
        if row.kind=='MEASURE' and row.verification_status=='VERIFIED' and data.action=='REVOKE':raise error(409,'MEASURE_EVENT_REQUIRED','已核验措施需通过撤销执行事件处理并记录文书')
        if data.action=='CONFIRM' and row.kind in {'CASE','MEASURE'} and person.verification_status!='VERIFIED':raise error(409,'PERSON_UNVERIFIED','人员身份尚未核验，不能确认该业务记录')
        target={'CONFIRM':'VERIFIED','RETURN':'RETURNED','REVOKE':'REVOKED'}[data.action]
        if db.execute(update(PersonRecord).where(PersonRecord.id==row.id,PersonRecord.version==data.version,PersonRecord.verification_status.in_(allowed)).values(verification_status=target,verified_by=user.id if target=='VERIFIED' else None,verified_at=now() if target=='VERIFIED' else None,version=PersonRecord.version+1)).rowcount!=1:raise error(409,'VERSION_OR_STATE_CONFLICT','业务状态或版本已变化')
        db.refresh(row)
        if data.action=='CONFIRM':
            if row.replaces_id:
                old=visible_record(db,user,row.replaces_id,error)
                if db.execute(update(PersonRecord).where(PersonRecord.id==old.id,PersonRecord.verification_status=='VERIFIED').values(verification_status='SUPERSEDED',version=PersonRecord.version+1)).rowcount!=1:raise error(409,'REPLACEMENT_CHANGED','原记录已改变，请核对更正关系')
                cancel_tasks(db,old)
            details=json.loads(row.details_json)
            if row.kind=='MEASURE':
                task(db,user,person,row,'END_CHECK','核对措施期限及解除依据',row.expected_end_on)
                task(db,user,person,row,'REPORT_CHECK','核对报到或执行情况',date.fromisoformat(details['report_due_on']) if details.get('report_due_on') else None)
            if row.kind in {'TEST','FOLLOWUP'}:task(db,user,person,row,'TEST' if row.kind=='TEST' else 'FOLLOWUP','后续检测或随访待办',date.fromisoformat(details['next_due_on']) if details.get('next_due_on') else None)
        elif data.action=='REVOKE':cancel_tasks(db,row)
        person.version+=1;add_event(db,user,person,'RECORD_'+data.action,data.note,row,{'document_no':data.document_no,'record':record_json(db,row)})
        audit(db,user,'PERSON_RECORD_REVIEW',row.id);result=record_json(db,row);finish(record,result,200,row.id);db.commit();return result

    @router.post('/records/{record_id}/execute')
    def execute(record_id:str,data:Execution,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'persons.treatment',error,'persons.read');row=visible_record(db,user,record_id,error);person=visible_person(db,user,row.person_id,error)
        if row.manager_org_id!=user.org_id or row.kind!='MEASURE':raise error(403,'FORBIDDEN','当前单位不能办理该措施')
        record,replay=reserve(db,user,'PERSON_MEASURE_EXECUTE',key,{'id':row.id,**data.model_dump(mode='json')})
        if replay:return replay
        if data.occurred_on>today() or data.occurred_on<row.occurred_on:raise error(422,'INVALID_EXECUTION_DATE','执行日期不得早于决定日期或晚于今天')
        if row.actual_start_on and data.occurred_on<row.actual_start_on:raise error(422,'INVALID_EXECUTION_DATE','结束或变更日期不得早于实际开始日期')
        start=data.action in {'REPORT','ADMIT'}
        if data.action=='REPORT' and row.record_type not in {'COMMUNITY','REHABILITATION'} or data.action=='ADMIT' and row.record_type not in {'ISOLATED','VOLUNTARY'}:raise error(422,'INVALID_EXECUTION_ACTION','执行动作与措施类型不匹配')
        target='ACTIVE' if start else {'RELEASE':'ENDED','CHANGE':'CHANGED','CANCEL':'CANCELLED'}[data.action]
        allowed=['DECIDED'] if start else ['DECIDED','ACTIVE']
        if db.execute(update(PersonRecord).where(PersonRecord.id==row.id,PersonRecord.version==data.version,PersonRecord.verification_status=='VERIFIED',PersonRecord.state.in_(allowed)).values(state=target,version=PersonRecord.version+1,**({'actual_start_on':data.occurred_on} if start else {'actual_end_on':data.occurred_on}))).rowcount!=1:raise error(409,'VERSION_OR_STATE_CONFLICT','措施需已核验且处于可办理状态，请重新查看')
        db.refresh(row)
        if start:db.execute(update(PersonTask).where(PersonTask.record_id==row.id,PersonTask.task_type=='REPORT_CHECK',PersonTask.status=='OPEN').values(status='DONE',result_note='已依据实际执行事件核对',completed_by=user.id,completed_at=now(),version=PersonTask.version+1))
        else:cancel_tasks(db,row)
        person.version+=1;add_event(db,user,person,'MEASURE_'+data.action,data.note,row,{**data.model_dump(mode='json'),'record':record_json(db,row)})
        audit(db,user,'PERSON_MEASURE_EXECUTE',row.id);result=record_json(db,row);finish(record,result,200,row.id);db.commit();return result

    @router.get('/{identity}/tasks')
    def tasks(identity:str,request:Request,page:int=Query(1,ge=1,le=100000),user:User=Depends(current_user),db:Session=Depends(get_db)):
        visible_person(db,user,identity,error)
        filters=[PersonTask.person_id==identity,PersonTask.org_id==user.org_id]
        total=db.scalar(select(func.count()).select_from(PersonTask).where(*filters)) or 0
        rows=db.scalars(select(PersonTask).where(*filters).order_by(PersonTask.status.desc(),PersonTask.due_on,PersonTask.id).offset((page-1)*20).limit(20)).all()
        result=page_result([{**{name:getattr(row,name) for name in ['id','record_id','task_type','title','due_on','status','result_note','version','completed_at']},'overdue':row.status=='OPEN' and row.due_on<today()} for row in rows],page,20,total,request_id(request));audit(db,user,'PERSON_TASK_VIEW',identity);db.commit();return result

    @router.post('/{identity}/tasks',status_code=201)
    def create_task(identity:str,data:TaskInput,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'persons.followup',error,'persons.read');need(db,user,'persons.health');person=visible_person(db,user,identity,error,True)
        if data.record_id:
            related=visible_record(db,user,data.record_id,error)
            if related.person_id!=person.id or related.manager_org_id!=user.org_id:raise error(404,'NOT_FOUND','关联业务不存在或无权办理')
        record,replay=reserve(db,user,'PERSON_TASK_CREATE',key,{'id':person.id,**data.model_dump(mode='json')})
        if replay:return replay
        bump(db,person,data.person_version);row=PersonTask(person_id=person.id,org_id=user.org_id,record_id=data.record_id,task_type=data.task_type,title=data.title,due_on=data.due_on,created_by=user.id)
        db.add(row);db.flush();add_event(db,user,person,'TASK_CREATED','新增人工待办',payload={'id':row.id,'due_on':row.due_on})
        audit(db,user,'PERSON_TASK_CREATE',row.id);result={'id':row.id,'version':row.version};finish(record,result,201,row.id);db.commit();return result

    @router.post('/tasks/{task_id}/complete')
    def complete_task(task_id:str,data:TaskComplete,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'persons.followup',error,'persons.read');need(db,user,'persons.health');row=db.get(PersonTask,task_id)
        if not row or row.org_id!=user.org_id:raise error(404,'NOT_FOUND','待办不存在或无权处理')
        person=visible_person(db,user,row.person_id,error)
        record,replay=reserve(db,user,'PERSON_TASK_COMPLETE',key,{'id':row.id,**data.model_dump()})
        if replay:return replay
        if db.execute(update(PersonTask).where(PersonTask.id==row.id,PersonTask.version==data.version,PersonTask.status=='OPEN').values(status=data.action,result_note=data.note,completed_by=user.id,completed_at=now(),version=PersonTask.version+1)).rowcount!=1:raise error(409,'VERSION_OR_STATE_CONFLICT','待办状态已变化')
        add_event(db,user,person,'TASK_'+data.action,data.note,payload={'id':row.id});audit(db,user,'PERSON_TASK_COMPLETE',row.id);result={'id':row.id,'status':data.action};finish(record,result,200,row.id);db.commit();return result

    @router.get('/{identity}/history')
    def history(identity:str,request:Request,page:int=Query(1,ge=1,le=100000),user:User=Depends(current_user),db:Session=Depends(get_db)):
        visible_person(db,user,identity,error);permissions=effective_permissions(db,user)
        visible_ids=select(PersonRecord.id).where(*record_filters(db,user,identity))
        filters=[PersonEvent.person_id==identity,or_(PersonEvent.record_id.in_(visible_ids), (PersonEvent.record_id.is_(None))&(PersonEvent.org_id==user.org_id))]
        if 'persons.identity' not in permissions:filters.append(~PersonEvent.action.in_(['IDENTITY_CONFIRM','IDENTITY_RETURN','IDENTITY_REVOKE','PROFILE_UPDATED']))
        if 'persons.health' not in permissions:filters.append(~PersonEvent.action.in_(['TASK_CREATED','TASK_DONE','TASK_CANCELLED']))
        if 'persons.transfer' not in permissions:filters.append(~PersonEvent.action.like('TRANSFER_%'))
        total=db.scalar(select(func.count()).select_from(PersonEvent).where(*filters)) or 0
        rows=db.scalars(select(PersonEvent).where(*filters).order_by(PersonEvent.created_at.desc(),PersonEvent.id.desc()).offset((page-1)*20).limit(20)).all()
        values=[]
        for row in rows:
            actor=db.get(User,row.actor_id)
            payload=json.loads(row.payload_json) if row.payload_json else None
            if row.action=='PROFILE_UPDATED' and payload:
                allowed={'id','name','source','document_type','document_number','document_mask','birth_date','phone','address','verification_status','version'}
                payload={phase:{key:value for key,value in record.items() if key in allowed} for phase,record in payload.items() if isinstance(record,dict)}
            values.append({'id':row.id,'record_id':row.record_id,'action':row.action,'note':row.note,'actor':actor.username if actor else '历史用户','created_at':row.created_at,'payload':payload})
        result=page_result(values,page,20,total,request_id(request));audit(db,user,'PERSON_HISTORY_VIEW',identity);db.commit();return result

    return router
