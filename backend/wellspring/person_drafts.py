"""Verified person profiles with scoped identity fields and legacy draft compatibility."""
from fastapi import APIRouter,Depends,Header,Query,Request
from fastapi.encoders import jsonable_encoder
from pydantic import Field
from sqlalchemy import exists,func,or_,select,update
from sqlalchemy.orm import Session
from .access_policy import effective_permissions
from .clue_deliveries import lock_flow
from .db import get_db
from .models import Case,PersonDraft,User,now
from .person_core import add_event,current_org,person_scope,profile_json,visible_person
from .person_models import PersonRecord
from .person_schemas import Input,PersonFields,PersonEdit,Review
from .security import current_user


class PersonSearch(Input):
    keyword:str=Field(default='',max_length=100)
    view:str=Field(default='all',pattern='^(all|case|drug|treatment|unverified)$')
    page:int=Field(default=1,ge=1,le=100000)
    page_size:int=Field(default=20,ge=1,le=100)


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix='/api/person-drafts',tags=['人员档案'])
    protected={'document_type','document_number','birth_date','phone','address'}
    def identity_fields(data,user,db):
        if 'persons.identity' not in effective_permissions(db,user) and any(name in data.model_fields_set and getattr(data,name) not in (None,'') for name in protected):
            raise error(403,'FORBIDDEN','当前账号没有完整身份信息权限')
        if data.document_number:
            if db.scalar(select(PersonDraft.id).where(person_scope(user),PersonDraft.document_type==data.document_type,PersonDraft.document_number==data.document_number,PersonDraft.id!=getattr(data,'id',''))):
                return True
        return False
    def handler(data,user,db):
        if data.responsible_user_id:
            target=db.get(User,data.responsible_user_id)
            if not target or not target.active or target.org_id!=user.org_id or 'persons.read' not in effective_permissions(db,target):raise error(422,'INVALID_HANDLER','责任人须为本单位启用且有人员查询权限的账号')
    def listing(data,request,user,db):
        permissions=effective_permissions(db,user);filters=[person_scope(user)]
        if data.keyword:filters.append(PersonDraft.name.contains(data.keyword,autoescape=True)|PersonDraft.source.contains(data.keyword,autoescape=True))
        if data.view=='unverified':filters.append(PersonDraft.verification_status!='VERIFIED')
        elif data.view=='case':
            if 'cases.read' not in permissions:raise error(403,'FORBIDDEN','缺少案件查询权限')
            filters.append(exists(select(PersonRecord.id).join(Case,Case.id==PersonRecord.case_id).where(PersonRecord.person_id==PersonDraft.id,PersonRecord.org_id==user.org_id,PersonRecord.kind=='CASE',PersonRecord.verification_status=='VERIFIED',Case.org_id==user.org_id)))
        elif data.view=='treatment':
            if 'persons.health' not in permissions:raise error(403,'FORBIDDEN','缺少敏感业务资料查询权限')
            filters.append(exists(select(PersonRecord.id).where(PersonRecord.person_id==PersonDraft.id,or_(PersonRecord.org_id==user.org_id,PersonRecord.manager_org_id==user.org_id),PersonRecord.kind=='MEASURE',PersonRecord.verification_status=='VERIFIED',PersonRecord.state.in_(['DECIDED','ACTIVE']))))
        elif data.view=='drug':
            if 'persons.health' not in permissions:raise error(403,'FORBIDDEN','缺少敏感业务资料查询权限')
            filters.append(exists(select(PersonRecord.id).where(PersonRecord.person_id==PersonDraft.id,or_(PersonRecord.org_id==user.org_id,PersonRecord.manager_org_id==user.org_id),PersonRecord.kind=='USE',PersonRecord.record_type.in_(['CONFIRMED','ADDICTION']),PersonRecord.verification_status=='VERIFIED')))
        total=db.scalar(select(func.count()).select_from(PersonDraft).where(*filters)) or 0
        rows=db.scalars(select(PersonDraft).where(*filters).order_by(PersonDraft.created_at.desc(),PersonDraft.id.desc()).offset((data.page-1)*data.page_size).limit(data.page_size)).all()
        result=page_result([profile_json(db,user,row) for row in rows],data.page,data.page_size,total,request_id(request))
        audit(db,user,'PERSON_DRAFT_SEARCH',user.org_id);db.commit();return result
    @router.get('')
    def list_people(request:Request,page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
        return listing(PersonSearch(page=page,page_size=page_size),request,user,db)
    @router.post('/search')
    def search_people(data:PersonSearch,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
        return listing(data,request,user,db)
    @router.post('',status_code=201)
    def create_person(data:PersonFields,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'persons.write',error,'persons.read')
        duplicate=identity_fields(data,user,db)
        record,replay=reserve(db,user,'PERSON_DRAFT_CREATE',key,data.model_dump())
        if replay:return replay
        if duplicate:raise error(409,'PERSON_DOCUMENT_EXISTS','当前授权范围已有相同证件档案，请先核对，系统不会自动合并')
        handler(data,user,db)
        row=PersonDraft(org_id=user.org_id,responsible_org_id=user.org_id,created_by=user.id,updated_by=user.id,verification_status='UNVERIFIED',**data.model_dump())
        db.add(row);db.flush();add_event(db,user,row,'PROFILE_CREATED','创建待核验人员主档')
        audit(db,user,'PERSON_DRAFT_CREATE',row.id);result=profile_json(db,user,row);finish(record,result,201,row.id);db.commit();return result
    @router.get('/options')
    def options(user:User=Depends(current_user),db:Session=Depends(get_db)):
        users=db.scalars(select(User).where(User.org_id==user.org_id,User.active.is_(True)).order_by(User.username).limit(500)).all()
        return {'users':[{'id':row.id,'name':row.username} for row in users],'actor_id':user.id}
    @router.get('/{identity}')
    def detail(identity:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=visible_person(db,user,identity,error);result=profile_json(db,user,row,True)
        audit(db,user,'PERSON_PROFILE_VIEW',row.id);db.commit();return result
    @router.post('/{identity}/update')
    def edit(identity:str,data:PersonEdit,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'persons.write',error,'persons.read');row=visible_person(db,user,identity,error,True)
        if 'persons.identity' not in effective_permissions(db,user) and protected&data.model_fields_set:raise error(403,'FORBIDDEN','当前账号不能修改身份字段')
        record,replay=reserve(db,user,'PERSON_PROFILE_EDIT',key,{'id':row.id,**data.model_dump()})
        if replay:return replay
        if data.document_number and db.scalar(select(PersonDraft.id).where(person_scope(user),PersonDraft.id!=row.id,PersonDraft.document_type==data.document_type,PersonDraft.document_number==data.document_number)):
            raise error(409,'PERSON_DOCUMENT_EXISTS','当前授权范围已有相同证件档案，请人工核对')
        handler(data,user,db);before=profile_json(db,user,row,True)
        values={name:getattr(data,name) for name in data.model_fields_set if name!='version'}
        values.update(version=PersonDraft.version+1,verification_status='UNVERIFIED',verified_by=None,verified_at=None,updated_by=user.id)
        if db.execute(update(PersonDraft).where(PersonDraft.id==row.id,PersonDraft.version==data.version).values(**values)).rowcount!=1:raise error(409,'VERSION_CONFLICT','人员档案已变化，请重新查看')
        db.refresh(row);add_event(db,user,row,'PROFILE_UPDATED','修改主档，身份需重新核验',payload={'before':before,'after':profile_json(db,user,row,True)})
        audit(db,user,'PERSON_PROFILE_EDIT',row.id);result=profile_json(db,user,row);finish(record,result,200,row.id);db.commit();return result
    @router.post('/{identity}/identity-review')
    def review(identity:str,data:Review,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'persons.verify',error,'persons.read');row=visible_person(db,user,identity,error,True)
        if 'persons.identity' not in effective_permissions(db,user):raise error(403,'FORBIDDEN','身份核验还需完整身份查询权限')
        record,replay=reserve(db,user,'PERSON_IDENTITY_REVIEW',key,{'id':row.id,**data.model_dump()})
        if replay:return replay
        if (row.updated_by or row.created_by)==user.id:raise error(403,'SELF_REVIEW','身份录入或最后修改人不能核验自己的资料')
        if data.action=='CONFIRM' and not row.document_number:raise error(422,'IDENTITY_INCOMPLETE','请先填写证件或其他身份依据编号')
        target='VERIFIED' if data.action=='CONFIRM' else 'RETURNED' if data.action=='RETURN' else 'UNVERIFIED'
        if data.action in {'CONFIRM','RETURN'} and row.verification_status=='VERIFIED':raise error(409,'IDENTITY_ALREADY_VERIFIED','已核验档案须通过撤销核验或主档更正处理')
        if db.execute(update(PersonDraft).where(PersonDraft.id==row.id,PersonDraft.version==data.version).values(verification_status=target,verified_by=user.id if target=='VERIFIED' else None,verified_at=now() if target=='VERIFIED' else None,version=PersonDraft.version+1)).rowcount!=1:raise error(409,'VERSION_CONFLICT','人员档案已变化')
        db.refresh(row);add_event(db,user,row,'IDENTITY_'+data.action,data.note,payload={'document_no':data.document_no})
        audit(db,user,'PERSON_IDENTITY_REVIEW',row.id);result=profile_json(db,user,row);finish(record,result,200,row.id);db.commit();return result
    return router
