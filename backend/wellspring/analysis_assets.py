"""Versioned authoring pages for modeling projects, business models and tactics."""
import json
from typing import Literal
from fastapi import APIRouter,Depends,Header,Query,Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import func,or_,select,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .access_policy import effective_permissions
from .analysis_models import AnalysisAsset as Asset,AnalysisAssetEvent as Event
from .analysis_rules import validate_config,sample_check
from .db import get_db
from .models import User,now
from .security import current_user
from .clue_deliveries import lock_flow

AREAS={'modeling':'PROJECT','models':'MODEL','tactics':'TACTIC'}


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)


class Fields(Input):
    name:str=Field(min_length=1,max_length=200)
    category:str=Field(min_length=1,max_length=30)
    description:str=Field(min_length=1,max_length=2000)
    configuration:dict
    project_id:str|None=Field(default=None,min_length=1,max_length=36)
    model_id:str|None=Field(default=None,min_length=1,max_length=36)


class Create(Fields):
    code:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')


class Edit(Fields):
    version:int=Field(ge=1)


class Search(Input):
    keyword:str=Field(default='',max_length=100)
    status:Literal['DRAFT','ACTIVE','ARCHIVED']|None=None
    category:str|None=Field(default=None,max_length=30)
    page:int=Field(default=1,ge=1,le=100000)


class Transition(Input):
    version:int=Field(ge=1)
    action:Literal['ACTIVATE','DEACTIVATE','ARCHIVE']
    note:str=Field(min_length=1,max_length=1000)


class Samples(Input):
    version:int=Field(ge=1)
    records:list[dict]=Field(min_length=1,max_length=100)


def asset_json(row,detail=False):
    result={name:getattr(row,name) for name in ['id','kind','code','name','category','description','project_id','model_id','status','version','created_at','updated_at']}
    if detail:result['configuration']=json.loads(row.config_json)
    return result


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix='/api/analysis',tags=['建模模型与技战法'])

    def kind(area):
        if area not in AREAS:raise error(404,'NOT_FOUND','页面不存在')
        return AREAS[area]

    def visible(db,user,area,identity):
        row=db.scalar(select(Asset).where(Asset.id==identity,Asset.org_id==user.org_id,Asset.kind==kind(area)))
        if not row:raise error(404,'NOT_FOUND','记录不存在或无权访问')
        return row

    def validate(data,user,db,area):
        try:validate_config(kind(area),data.category,data.configuration)
        except (ValueError,TypeError,RecursionError):raise error(422,'INVALID_CONFIGURATION','配置结构无效，请按字段示例检查内容') from None
        for identity,expected,permission in [(data.project_id,'PROJECT','modeling.read'),(data.model_id,'MODEL','models.read')]:
            if not identity:continue
            if (kind(area)=='PROJECT') or (kind(area)=='MODEL' and expected=='MODEL'):raise error(422,'INVALID_RELATION','当前记录不接受该类关联')
            row=db.scalar(select(Asset).where(Asset.id==identity,Asset.org_id==user.org_id,Asset.kind==expected,Asset.status!='ARCHIVED'))
            if not row or permission not in effective_permissions(db,user):raise error(404,'NOT_FOUND','关联记录不存在或无权访问')

    def snapshot(db,user,row,action,note):
        db.add(Event(asset_id=row.id,org_id=user.org_id,actor_id=user.id,action=action,note=note,snapshot_json=json.dumps(jsonable_encoder(asset_json(row,True)),ensure_ascii=False)))

    @router.post('/{area}/search')
    def search(area:str,data:Search,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
        filters=[Asset.kind==kind(area),Asset.org_id==user.org_id]
        if data.keyword:filters.append(Asset.name.contains(data.keyword,autoescape=True)|Asset.code.contains(data.keyword,autoescape=True))
        if data.status:filters.append(Asset.status==data.status)
        if data.category:filters.append(Asset.category==data.category)
        total=db.scalar(select(func.count()).select_from(Asset).where(*filters)) or 0
        rows=db.scalars(select(Asset).where(*filters).order_by(Asset.updated_at.desc(),Asset.id.desc()).offset((data.page-1)*20).limit(20)).all()
        audit(db,user,'ANALYSIS_ASSET_SEARCH',user.org_id);db.commit();return page_result([asset_json(row) for row in rows],data.page,20,total,request_id(request))

    @router.get('/{area}/options')
    def options(area:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        kind(area);result={}
        for prefix,expected in [('modeling','PROJECT'),('models','MODEL')]:
            rows=db.scalars(select(Asset).where(Asset.org_id==user.org_id,Asset.kind==expected,Asset.status!='ARCHIVED').order_by(Asset.name).limit(501)).all() if area!='modeling' and not (area=='models' and prefix=='models') and prefix+'.read' in effective_permissions(db,user) else []
            if len(rows)>500:raise error(422,'OPTIONS_TOO_LARGE','关联选项超过 500 项，请先收敛资料范围')
            result[prefix]=[{'id':row.id,'name':row.name,'code':row.code,'status':row.status} for row in rows]
        return result

    @router.post('/{area}',status_code=201)
    def create(area:str,data:Create,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        kind(area);lock_flow(db,user,area+'.write',error,area+'.read');validate(data,user,db,area);record,replay=reserve(db,user,'ANALYSIS_CREATE_'+kind(area),key,data.model_dump())
        if replay:return replay
        row=Asset(org_id=user.org_id,kind=kind(area),code=data.code,name=data.name,category=data.category,description=data.description,config_json=json.dumps(data.configuration,ensure_ascii=False),project_id=data.project_id,model_id=data.model_id,created_by=user.id,updated_by=user.id)
        db.add(row)
        try:db.flush()
        except IntegrityError:
            db.rollback();raise error(409,'CODE_EXISTS','当前组织已有相同编号，请换用其他编号') from None
        snapshot(db,user,row,'CREATED','创建草稿');audit(db,user,'ANALYSIS_ASSET_CREATE',row.id);result=asset_json(row,True);finish(record,result,201,row.id);db.commit();return result

    @router.get('/{area}/{identity}')
    def detail(area:str,identity:str,request:Request,page:int=Query(1,ge=1,le=100000),user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=visible(db,user,area,identity)
        total=db.scalar(select(func.count()).select_from(Event).where(Event.asset_id==row.id)) or 0
        events=db.scalars(select(Event).where(Event.asset_id==row.id).order_by(Event.created_at.desc(),Event.id.desc()).offset((page-1)*20).limit(20)).all()
        result={'asset':asset_json(row,True),'history':page_result([{'id':event.id,'action':event.action,'note':event.note,'created_at':event.created_at,'snapshot':json.loads(event.snapshot_json)} for event in events],page,20,total,request_id(request))}
        audit(db,user,'ANALYSIS_ASSET_VIEW',row.id);db.commit();return result

    @router.post('/{area}/{identity}/update')
    def edit(area:str,identity:str,data:Edit,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        kind(area);lock_flow(db,user,area+'.write',error,area+'.read');row=visible(db,user,area,identity);validate(data,user,db,area);record,replay=reserve(db,user,'ANALYSIS_UPDATE',key,{'id':row.id,**data.model_dump()})
        if replay:return replay
        changed=db.execute(update(Asset).where(Asset.id==row.id,Asset.version==data.version,Asset.status=='DRAFT').values(name=data.name,category=data.category,description=data.description,config_json=json.dumps(data.configuration,ensure_ascii=False),project_id=data.project_id,model_id=data.model_id,updated_by=user.id,updated_at=now(),version=Asset.version+1)).rowcount
        if not changed:raise error(409,'VERSION_OR_STATE_CONFLICT','仅草稿可编辑，请停用或重新查看最新版本')
        db.refresh(row);snapshot(db,user,row,'UPDATED','修改草稿');audit(db,user,'ANALYSIS_ASSET_UPDATE',row.id);result=asset_json(row,True);finish(record,result,200,row.id);db.commit();return result

    @router.post('/{area}/{identity}/transition')
    def transition(area:str,identity:str,data:Transition,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        kind(area);lock_flow(db,user,area+'.write',error,area+'.read');row=visible(db,user,area,identity);record,replay=reserve(db,user,'ANALYSIS_TRANSITION',key,{'id':row.id,**data.model_dump()})
        if replay:return replay
        target={'ACTIVATE':'ACTIVE','DEACTIVATE':'DRAFT','ARCHIVE':'ARCHIVED'}[data.action];before='ACTIVE' if data.action=='DEACTIVATE' else 'DRAFT'
        if target=='ACTIVE':
            permissions=effective_permissions(db,user)
            if row.project_id and 'modeling.read' not in permissions or row.model_id and 'models.read' not in permissions:
                raise error(403,'FORBIDDEN','启用前需有权查看关联的建模项目或业务模型')
            for identity_ref in [row.project_id,row.model_id]:
                if identity_ref:
                    related=db.scalar(select(Asset).where(Asset.id==identity_ref,Asset.org_id==user.org_id,Asset.status=='ACTIVE'))
                    if not related:raise error(409,'RELATION_INACTIVE','请先启用关联的建模项目或业务模型')
        else:
            if db.scalar(select(Asset.id).where(Asset.org_id==user.org_id,Asset.status=='ACTIVE',or_(Asset.project_id==row.id,Asset.model_id==row.id)).limit(1)):
                raise error(409,'ASSET_IN_USE','存在启用中的关联模型或技战法，请先停用关联记录')
        if db.execute(update(Asset).where(Asset.id==row.id,Asset.version==data.version,Asset.status==before).values(status=target,version=Asset.version+1,updated_by=user.id,updated_at=now())).rowcount!=1:raise error(409,'VERSION_OR_STATE_CONFLICT','状态或版本已改变，请重新查看')
        db.refresh(row);snapshot(db,user,row,data.action,data.note);audit(db,user,'ANALYSIS_ASSET_'+data.action,row.id);result=asset_json(row,True);finish(record,result,200,row.id);db.commit();return result

    @router.post('/models/{identity}/validate')
    def test_model(identity:str,data:Samples,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=visible(db,user,'models',identity)
        if row.version!=data.version or row.status=='ARCHIVED':raise error(409,'VERSION_OR_STATE_CONFLICT','模型版本已变化或已经归档，请重新查看')
        try:result=sample_check(row.category,json.loads(row.config_json),data.records)
        except (ValueError,TypeError,RecursionError):raise error(422,'INVALID_SAMPLE','样例结构或长度无效，请使用字段对象数组') from None
        audit(db,user,'ANALYSIS_MODEL_SAMPLE',row.id);db.commit();return {**result,'version':row.version}

    return router
