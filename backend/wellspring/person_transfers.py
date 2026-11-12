"""Explicit responsibility handoff; share active measure episodes, not all case history."""
from fastapi import APIRouter,Depends,Header,Query,Request
from sqlalchemy import func,or_,select,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .clue_deliveries import lock_flow
from .db import get_db
from .models import Organization,PersonDraft,User,now
from .person_core import add_event,current_org,mask,visible_person
from .person_models import PersonRecord,PersonTask,PersonTransfer
from .person_schemas import TransferInput,TransferAction
from .security import current_user


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix='/api/person-drafts',tags=['人员责任交接'])
    def render(db,row):
        person=db.get(PersonDraft,row.person_id);source=db.get(Organization,row.source_org_id);target=db.get(Organization,row.target_org_id)
        return {**{key:getattr(row,key) for key in ['id','person_id','source_org_id','target_org_id','reason','response_note','status','version','created_at','completed_at']},
            'name':person.name,'document_mask':mask(person.document_number),'source_org':source.name if source else '', 'target_org':target.name if target else ''}
    @router.get('/transfers/options')
    def options(user:User=Depends(current_user),db:Session=Depends(get_db)):
        rows=db.scalars(select(Organization).where(Organization.active.is_(True),Organization.id!=user.org_id).order_by(Organization.name).limit(1000)).all()
        return {'organizations':[{'id':row.id,'name':row.name} for row in rows],'current_org_id':user.org_id}
    @router.get('/transfers/inbox')
    def inbox(request:Request,page:int=Query(1,ge=1,le=100000),focus_id:str|None=Query(None,max_length=36),user:User=Depends(current_user),db:Session=Depends(get_db)):
        filters=[or_(PersonTransfer.source_org_id==user.org_id,PersonTransfer.target_org_id==user.org_id)]
        if focus_id:filters.append(PersonTransfer.id==focus_id)
        total=db.scalar(select(func.count()).select_from(PersonTransfer).where(*filters)) or 0
        rows=db.scalars(select(PersonTransfer).where(*filters).order_by(PersonTransfer.created_at.desc(),PersonTransfer.id.desc()).offset((page-1)*20).limit(20)).all()
        result=page_result([render(db,row) for row in rows],page,20,total,request_id(request));audit(db,user,'PERSON_TRANSFER_INBOX',user.org_id);db.commit();return result
    @router.post('/{identity}/transfers',status_code=201)
    def request_transfer(identity:str,data:TransferInput,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'persons.transfer',error,'persons.read');person=visible_person(db,user,identity,error,True)
        record,replay=reserve(db,user,'PERSON_TRANSFER_REQUEST',key,{'id':person.id,**data.model_dump()})
        if replay:return replay
        if person.verification_status!='VERIFIED':raise error(409,'PERSON_UNVERIFIED','请先核验身份，再办理责任移交')
        target=db.get(Organization,data.target_org_id)
        if not target or not target.active or target.id==user.org_id:raise error(422,'INVALID_TARGET','请选择其他启用单位')
        if db.scalar(select(PersonRecord.id).where(PersonRecord.person_id==person.id,PersonRecord.kind=='MEASURE',PersonRecord.manager_org_id==user.org_id,PersonRecord.verification_status.in_(['PENDING','RETURNED']))):raise error(409,'RECORDS_PENDING','请先处理本单位待核验的措施，再办理移交')
        if db.execute(update(PersonDraft).where(PersonDraft.id==person.id,PersonDraft.version==data.person_version).values(version=PersonDraft.version+1)).rowcount!=1:raise error(409,'VERSION_CONFLICT','人员档案已变化')
        row=PersonTransfer(person_id=person.id,source_org_id=user.org_id,target_org_id=target.id,requested_by=user.id,reason=data.reason);db.add(row)
        try:db.flush()
        except IntegrityError:
            db.rollback();raise error(409,'TRANSFER_PENDING','已有待接收的移交申请，请勿重复发起') from None
        add_event(db,user,person,'TRANSFER_REQUEST',data.reason);audit(db,user,'PERSON_TRANSFER_REQUEST',row.id);result=render(db,row);finish(record,result,201,row.id);db.commit();return result
    @router.post('/transfers/{transfer_id}/resolve')
    def resolve(transfer_id:str,data:TransferAction,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'persons.transfer',error,'persons.read');row=db.get(PersonTransfer,transfer_id)
        if not row or user.org_id not in {row.source_org_id,row.target_org_id}:raise error(404,'NOT_FOUND','移交记录不存在或无权访问')
        if data.action=='CANCEL' and user.org_id!=row.source_org_id or data.action in {'ACCEPT','REJECT'} and user.org_id!=row.target_org_id:raise error(403,'FORBIDDEN','接收单位确认或退回，发起单位可撤销未完成申请')
        record,replay=reserve(db,user,'PERSON_TRANSFER_RESOLVE',key,{'id':row.id,**data.model_dump()})
        if replay:return replay
        person=db.get(PersonDraft,row.person_id)
        if current_org(person)!=row.source_org_id:raise error(409,'RESPONSIBILITY_CHANGED','当前责任单位已变化，请重新核对')
        if data.action=='ACCEPT':
            org=db.get(Organization,user.org_id)
            if not org.active:raise error(409,'ORGANIZATION_INACTIVE','接收单位已停用')
            if person.document_number and db.scalar(select(PersonDraft.id).where(PersonDraft.id!=person.id,or_(PersonDraft.org_id==user.org_id,PersonDraft.responsible_org_id==user.org_id),PersonDraft.document_type==person.document_type,PersonDraft.document_number==person.document_number)):
                raise error(409,'DUPLICATE_REVIEW_REQUIRED','本单位已有相同证件档案，请先人工核对；不会自动合并或覆盖')
        target={'ACCEPT':'ACCEPTED','REJECT':'REJECTED','CANCEL':'CANCELLED'}[data.action]
        if db.execute(update(PersonTransfer).where(PersonTransfer.id==row.id,PersonTransfer.version==data.version,PersonTransfer.status=='PENDING').values(status=target,response_note=data.note,accepted_by=user.id,completed_at=now(),version=PersonTransfer.version+1)).rowcount!=1:raise error(409,'VERSION_OR_STATE_CONFLICT','移交已经处理或版本变化')
        if data.action=='ACCEPT':
            person.responsible_org_id=user.org_id;person.responsible_user_id=None;person.version+=1
            active_ids=select(PersonRecord.id).where(PersonRecord.person_id==person.id,PersonRecord.kind=='MEASURE',PersonRecord.manager_org_id==row.source_org_id,PersonRecord.verification_status=='VERIFIED',PersonRecord.state.in_(['DECIDED','ACTIVE']))
            ids=list(db.scalars(active_ids))
            if ids:db.execute(update(PersonRecord).where(PersonRecord.id.in_(ids)).values(manager_org_id=user.org_id,version=PersonRecord.version+1))
            db.execute(update(PersonTask).where(PersonTask.person_id==person.id,PersonTask.org_id==row.source_org_id,PersonTask.status=='OPEN').values(org_id=user.org_id,version=PersonTask.version+1))
        db.flush();db.refresh(row);result=render(db,row)
        add_event(db,user,person,'TRANSFER_'+data.action,data.note);audit(db,user,'PERSON_TRANSFER_RESOLVE',row.id)
        finish(record,result,200,row.id);db.commit();return result
    return router
