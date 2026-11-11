"""Hierarchical distribution with immutable scope restrictions and stepwise feedback."""
from datetime import date,timezone,timedelta
import json
from typing import Literal
from fastapi import APIRouter,Depends,Header,Request
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import func,or_,select,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Clue,Organization,User,Session as LoginSession,now
from .access_models import AdministrationLock
from .intelligence_models import ClueDelivery as Delivery,DeliveryEvent
from .security import current_user
from .access_policy import effective_permissions

LEVELS={'CITY':0,'BRANCH':1,'STATION':2}


def lock_flow(db,user,permission,error,read_permission='intelligence.read'):
    """Share the administration mutex so hierarchy/account changes cannot race dispatch."""
    original_org,session_hash=user.org_id,user._authenticated_session
    if db.get_bind().dialect.name=='sqlite':from sqlalchemy.dialects.sqlite import insert
    else:from sqlalchemy.dialects.postgresql import insert
    db.execute(insert(AdministrationLock).values(id='accounts',version=1).on_conflict_do_nothing(index_elements=['id']))
    db.execute(update(AdministrationLock).where(AdministrationLock.id=='accounts').values(version=AdministrationLock.version+1))
    db.expire_all();db.refresh(user)
    if not user.active or user.org_id!=original_org or not db.get(LoginSession,session_hash):raise error(401,'UNAUTHENTICATED','账号或组织授权已变化，请重新登录')
    org=db.get(Organization,user.org_id)
    if not org or not org.active or not {read_permission,permission}<=effective_permissions(db,user):raise error(403,'FORBIDDEN','当前账号无此办理权限')


def descendants(db,organization_id):
    rows=db.scalars(select(Organization)).all()
    children={}
    for row in rows:children.setdefault(row.parent_id,[]).append(row)
    result=[];pending=[organization_id];seen={organization_id}
    while pending:
        parent=pending.pop()
        for row in children.get(parent,[]):
            if row.id in seen or not row.active:continue
            seen.add(row.id);result.append(row);pending.append(row.id)
    return result


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)


class Dispatch(Input):
    version:int=Field(ge=1)
    recipient_org_id:str=Field(min_length=1,max_length=36)
    objective:str=Field(min_length=1,max_length=2000)
    due_date:date|None=None
    allow_station:bool=False


class Action(Input):
    version:int=Field(ge=1)
    note:str=Field(default='',max_length=5000)


class Feedback(Action):
    disposition:str=Field(min_length=1,max_length=5000)
    feedback:str=Field(min_length=1,max_length=5000)
    result:Literal['VERIFIED','NO_FINDING','INSUFFICIENT','DUPLICATE','TRANSFER','CONTINUE']


class Resolve(Action):
    action:Literal['RETURN','CLOSE']


class Reassign(Action):
    assignee_id:str=Field(min_length=1,max_length=36)


class Search(Input):
    scope:Literal['received','sent']='received'
    keyword:str=Field(default='',max_length=100)
    status:Literal['OPEN','PROCESSING','PENDING_REVIEW','RETURNED','CLOSED']|None=None
    mine:bool=False
    overdue:bool=False
    page:int=Field(default=1,ge=1,le=100000)


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix='/api/intelligence',tags=['线索层级流转'])

    def visible(db,user,identity):
        row=db.get(Delivery,identity)
        if not row:raise error(404,'NOT_FOUND','流转记录不存在或无权访问')
        clue=db.get(Clue,row.clue_id)
        if row.sender_org_id==user.org_id or row.recipient_org_id==user.org_id or clue.org_id==user.org_id:return row
        parent_id=row.parent_id;seen=set()
        while parent_id and parent_id not in seen:
            seen.add(parent_id);parent=db.get(Delivery,parent_id)
            if not parent:break
            if parent.recipient_org_id==user.org_id:return row
            parent_id=parent.parent_id
        raise error(404,'NOT_FOUND','流转记录不存在或无权访问')

    def render(db,row):
        sender=db.get(Organization,row.sender_org_id);recipient=db.get(Organization,row.recipient_org_id)
        actor=db.get(User,row.assignee_id) if row.assignee_id else None
        return {**{key:getattr(row,key) for key in ['id','clue_id','parent_id','sender_org_id','recipient_org_id','objective','due_date','allow_station','status','version','assignee_id','created_at','accepted_at','feedback_at','closed_at','disposition_text','feedback_text','result_code']},
            'sender_name':sender.name if sender else '', 'recipient_name':recipient.name if recipient else '',
            'assignee_name':actor.username if actor else None,'snapshot':json.loads(row.snapshot_json),
            'overdue':bool(row.due_date and row.due_date<now().astimezone(timezone(timedelta(hours=8))).date() and row.status!='CLOSED')}

    def event(db,user,row,action,note,before=None,payload=None):
        db.add(DeliveryEvent(delivery_id=row.id,actor_id=user.id,actor_org_id=user.org_id,action=action,note=note,
            before_status=before,after_status=row.status,payload_json=json.dumps(payload,ensure_ascii=False,default=str) if payload else None))

    def eligible(db,user,parent=None):
        org=db.get(Organization,user.org_id)
        if org.unit_type not in {'CITY','BRANCH'}:return []
        return [item for item in descendants(db,user.org_id) if item.unit_type in LEVELS and LEVELS[item.unit_type]>=LEVELS[org.unit_type]
                and not (org.unit_type=='CITY' and item.unit_type=='STATION')
                and (parent is None or parent.allow_station or item.unit_type!='STATION')]

    @router.get('/delivery-options')
    def options(parent_id:str|None=None,user:User=Depends(current_user),db:Session=Depends(get_db)):
        parent=visible(db,user,parent_id) if parent_id else None
        if parent and parent.recipient_org_id!=user.org_id:raise error(403,'FORBIDDEN','只有接收单位可以继续下发')
        values=[{'id':org.id,'name':org.name,'unit_type':org.unit_type,'parent_id':org.parent_id} for org in eligible(db,user,parent)]
        return {'organizations':values,'current_org_id':user.org_id,'current_org_type':db.get(Organization,user.org_id).unit_type,'actor_id':user.id}

    def dispatch(data,user,db,key,clue_id=None,parent_id=None):
        lock_flow(db,user,'intelligence.dispatch',error)
        parent=visible(db,user,parent_id) if parent_id else None
        if parent:
            if parent.recipient_org_id!=user.org_id or parent.status not in {'PROCESSING','RETURNED'}:
                raise error(409,'INVALID_FLOW_STATE','请先接收线索，处置中或退回补充时才可继续下发')
            if data.allow_station and not parent.allow_station:raise error(403,'FORWARD_RESTRICTED','上级禁止下发派出所，下级不得放宽限制')
            clue=db.get(Clue,parent.clue_id);snapshot=json.loads(parent.snapshot_json)
        else:
            clue=db.scalar(select(Clue).where(Clue.id==clue_id,Clue.org_id==user.org_id))
            if not clue:raise error(404,'NOT_FOUND','线索不存在或无权下发')
            if clue.status!='REVIEWED':raise error(409,'NOT_REVIEWED','线索核验后才能下发')
            snapshot={key:getattr(clue,key) for key in ['title','summary','source','reference_no','priority']}
        target=next((org for org in eligible(db,user,parent) if org.id==data.recipient_org_id),None)
        if not target:raise error(403,'INVALID_RECIPIENT','仅能下发给启用的下级分局/大队或获准的派出所，请检查组织类型和层级')
        if target.unit_type=='STATION' and not data.allow_station:raise error(403,'FORWARD_RESTRICTED','本条线索禁止下发派出所')
        if snapshot.get('priority')=='IMPORTANT' and data.allow_station:raise error(403,'FORWARD_RESTRICTED','重要线索禁止下发派出所，不能放宽限制')
        deadline=data.due_date or (parent.due_date if parent else clue.suggested_due_date)
        if parent and parent.due_date and deadline and deadline>parent.due_date:raise error(422,'DEADLINE_EXCEEDED','下级办理期限不能晚于上级期限')
        record,replay=reserve(db,user,'CLUE_DISPATCH',key,{'clue_id':clue.id,'parent_id':parent_id,**data.model_dump(mode='json')})
        if replay:return replay
        model=Delivery if parent else Clue;identity=parent.id if parent else clue.id
        conditions=[model.id==identity,model.version==data.version]
        if parent:conditions.append(Delivery.status.in_(['PROCESSING','RETURNED']))
        else:conditions.append(Clue.status=='REVIEWED')
        if db.execute(update(model).where(*conditions).values(version=model.version+1)).rowcount!=1:
            raise error(409,'VERSION_CONFLICT','记录已变化，请重新查看')
        row=Delivery(clue_id=clue.id,parent_id=parent_id,sender_org_id=user.org_id,recipient_org_id=target.id,sender_id=user.id,
            objective=data.objective,due_date=deadline,allow_station=data.allow_station,snapshot_json=json.dumps(snapshot,ensure_ascii=False))
        db.add(row)
        try:db.flush()
        except IntegrityError:
            db.rollback();raise error(409,'DELIVERY_EXISTS','该单位已有未办结的同条线索，不能重复下发') from None
        event(db,user,row,'DISPATCH','线索已下发',payload={'objective':row.objective,'due_date':deadline,'allow_station':row.allow_station})
        audit(db,user,'CLUE_DISPATCH',row.id);result=render(db,row);finish(record,result,201,row.id);db.commit();return result

    @router.post('/clues/{clue_id}/dispatch',status_code=201)
    def root_dispatch(clue_id:str,data:Dispatch,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        return dispatch(data,user,db,key,clue_id=clue_id)

    @router.post('/deliveries/{identity}/dispatch',status_code=201)
    def forward(identity:str,data:Dispatch,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        return dispatch(data,user,db,key,parent_id=identity)

    @router.post('/deliveries/search')
    def search(data:Search,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
        filters=[(Delivery.recipient_org_id if data.scope=='received' else Delivery.sender_org_id)==user.org_id]
        if data.status:filters.append(Delivery.status==data.status)
        if data.mine:filters.append(Delivery.assignee_id==user.id)
        if data.keyword:filters.append(Delivery.objective.contains(data.keyword,autoescape=True)|Delivery.snapshot_json.contains(data.keyword,autoescape=True))
        if data.overdue:filters.extend([Delivery.due_date<now().astimezone(timezone(timedelta(hours=8))).date(),Delivery.status!='CLOSED'])
        total=db.scalar(select(func.count()).select_from(Delivery).where(*filters)) or 0
        rows=db.scalars(select(Delivery).where(*filters).order_by(Delivery.created_at.desc(),Delivery.id.desc()).offset((data.page-1)*20).limit(20)).all()
        audit(db,user,'CLUE_DELIVERY_SEARCH',user.org_id);db.commit()
        return page_result([render(db,row) for row in rows],data.page,20,total,request_id(request))

    @router.get('/deliveries/{identity}')
    def detail(identity:str,request:Request,page:int=1,child_page:int=1,user:User=Depends(current_user),db:Session=Depends(get_db)):
        if not 1<=page<=100000 or not 1<=child_page<=100000:raise error(422,'VALIDATION_ERROR','页码无效')
        row=visible(db,user,identity)
        child_total=db.scalar(select(func.count()).select_from(Delivery).where(Delivery.parent_id==row.id)) or 0
        pending_children=db.scalar(select(func.count()).select_from(Delivery).where(Delivery.parent_id==row.id,Delivery.status!='CLOSED')) or 0
        child_rows=db.scalars(select(Delivery).where(Delivery.parent_id==row.id).order_by(Delivery.created_at,Delivery.id).offset((child_page-1)*20).limit(20)).all()
        stmt=select(DeliveryEvent).where(DeliveryEvent.delivery_id==row.id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        events=db.scalars(stmt.order_by(DeliveryEvent.created_at,DeliveryEvent.id).offset((page-1)*20).limit(20)).all()
        values=[]
        for entry in events:
            actor=db.get(User,entry.actor_id);org=db.get(Organization,entry.actor_org_id)
            values.append({**{name:getattr(entry,name) for name in ['id','action','note','before_status','after_status','created_at']},
                'actor':actor.username if actor else '历史用户','organization':org.name if org else '', 'payload':json.loads(entry.payload_json) if entry.payload_json else None})
        audit(db,user,'CLUE_DELIVERY_VIEW',row.id);db.commit()
        return {'delivery':render(db,row),'children':[render(db,child) for child in child_rows], 'children_total':child_total,'children_page':child_page,'pending_children':pending_children,'events':page_result(values,page,20,total,request_id(request)),
            'can_handle':row.recipient_org_id==user.org_id,'can_resolve':row.sender_org_id==user.org_id,'actor_id':user.id}

    def change(identity,data,user,db,key,action):
        lock_flow(db,user,'intelligence.review' if action=='RESOLVE' else 'intelligence.dispose',error)
        row=visible(db,user,identity);before=row.status
        if action=='RESOLVE':
            if row.sender_org_id!=user.org_id:raise error(403,'FORBIDDEN','只有下发单位可以复核本级反馈')
            if row.assignee_id==user.id:raise error(403,'FORBIDDEN','反馈提交人不能复核自己的反馈')
            if not data.note:raise error(422,'VALIDATION_ERROR','请填写复核意见')
            allowed=['PENDING_REVIEW'];target='CLOSED' if data.action=='CLOSE' else 'RETURNED'
            values={'status':target,**({'closed_at':now()} if target=='CLOSED' else {})}
        else:
            if row.recipient_org_id!=user.org_id:raise error(403,'FORBIDDEN','只有接收单位可以处置或反馈')
            if action=='ACCEPT':
                allowed=['OPEN'];target='PROCESSING';values={'status':target,'assignee_id':user.id,'accepted_at':now()}
            else:
                if row.assignee_id!=user.id:raise error(403,'FORBIDDEN','仅当前承办人可以登记处置或反馈')
                allowed=['PROCESSING','RETURNED'];target=before
                if action=='PROGRESS':
                    if not data.note:raise error(422,'VALIDATION_ERROR','请填写处置记录')
                    values={'disposition_text':data.note}
                else:
                    if db.scalar(select(Delivery.id).where(Delivery.parent_id==row.id,Delivery.status!='CLOSED').limit(1)):
                        raise error(409,'CHILDREN_PENDING','请先复核办结全部下级反馈，再向上级提交汇总反馈')
                    target='PENDING_REVIEW';values={'status':target,'disposition_text':data.disposition,'feedback_text':data.feedback,'result_code':data.result,'feedback_at':now()}
        record,replay=reserve(db,user,'DELIVERY_'+action,key,{'id':row.id,**data.model_dump(mode='json')})
        if replay:return replay
        conditions=[Delivery.id==row.id,Delivery.version==data.version,Delivery.status.in_(allowed)]
        if action=='ACCEPT':conditions.append(Delivery.assignee_id.is_(None))
        values['version']=Delivery.version+1
        if db.execute(update(Delivery).where(*conditions).values(**values)).rowcount!=1:raise error(409,'VERSION_OR_STATE_CONFLICT','流转状态或版本已改变，请重新查看')
        db.refresh(row);event(db,user,row,data.action if action=='RESOLVE' else action,data.note or {'ACCEPT':'已接收并开始承办','FEEDBACK':'已提交反馈'}.get(action,''),before,data.model_dump(mode='json'))
        audit(db,user,'DELIVERY_'+action,row.id);result=render(db,row);finish(record,result,200,row.id);db.commit();return result

    @router.post('/deliveries/{identity}/accept')
    def accept(identity:str,data:Action,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):return change(identity,data,user,db,key,'ACCEPT')

    @router.post('/deliveries/{identity}/progress')
    def progress(identity:str,data:Action,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):return change(identity,data,user,db,key,'PROGRESS')

    @router.post('/deliveries/{identity}/feedback')
    def feedback(identity:str,data:Feedback,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):return change(identity,data,user,db,key,'FEEDBACK')

    @router.post('/deliveries/{identity}/resolve')
    def resolve(identity:str,data:Resolve,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):return change(identity,data,user,db,key,'RESOLVE')

    @router.get('/delivery-handlers')
    def handlers(user:User=Depends(current_user),db:Session=Depends(get_db)):
        rows=db.scalars(select(User).where(User.org_id==user.org_id,User.active.is_(True)).order_by(User.username).limit(1000)).all()
        return [{'id':row.id,'username':row.username} for row in rows if {'intelligence.read','intelligence.dispose'}<=effective_permissions(db,row)]

    @router.post('/deliveries/{identity}/reassign')
    def reassign(identity:str,data:Reassign,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'intelligence.dispatch',error)
        row=visible(db,user,identity)
        if row.recipient_org_id!=user.org_id:raise error(403,'FORBIDDEN','仅接收单位可转交承办')
        if not data.note:raise error(422,'VALIDATION_ERROR','请填写转交原因')
        target=db.get(User,data.assignee_id)
        if not target or not target.active or target.org_id!=user.org_id or not {'intelligence.read','intelligence.dispose'}<=effective_permissions(db,target):raise error(422,'INVALID_ASSIGNEE','承办人须为本单位启用且具有处置权限的账号')
        record,replay=reserve(db,user,'DELIVERY_REASSIGN',key,{'id':row.id,**data.model_dump()})
        if replay:return replay
        before=row.status
        if row.assignee_id==target.id:raise error(409,'SAME_ASSIGNEE','当前已由该账号承办')
        if db.execute(update(Delivery).where(Delivery.id==row.id,Delivery.version==data.version,Delivery.status.in_(['OPEN','PROCESSING','RETURNED'])).values(assignee_id=target.id,status='PROCESSING',accepted_at=now(),version=Delivery.version+1)).rowcount!=1:raise error(409,'VERSION_OR_STATE_CONFLICT','当前状态不允许转交，或记录已变化')
        db.refresh(row);event(db,user,row,'REASSIGN',data.note,before,{'assignee_id':target.id});audit(db,user,'DELIVERY_REASSIGN',row.id)
        result=render(db,row);finish(record,result,200,row.id);db.commit();return result

    return router
