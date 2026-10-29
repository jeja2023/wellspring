"""盘点差异调查与复核草稿；不调整证物余额。"""
from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Evidence, EvidenceInventoryObservation, InventoryInvestigation, InventoryInvestigationEvent, User
from .security import current_user

class StartInvestigation(BaseModel):
    note: str = Field(min_length=1,max_length=1000)

class InvestigationTransition(BaseModel):
    version: int = Field(ge=1)
    action: Literal["SUBMIT","RETURN","REVIEW"]
    note: str = Field(min_length=1,max_length=1000)


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix="/api/evidence",tags=["证物盘点调查（开发验证）"])
    def visible_observation(db,user,observation_id):
        row=db.scalar(select(EvidenceInventoryObservation).join(Evidence,Evidence.id==EvidenceInventoryObservation.evidence_id).where(
            EvidenceInventoryObservation.id==observation_id,EvidenceInventoryObservation.org_id==user.org_id,Evidence.org_id==user.org_id))
        if not row:raise error(404,"NOT_FOUND","记录不存在或无权访问")
        return row
    def visible_investigation(db,user,investigation_id):
        row=db.scalar(select(InventoryInvestigation).where(InventoryInvestigation.id==investigation_id,InventoryInvestigation.org_id==user.org_id))
        if not row:raise error(404,"NOT_FOUND","记录不存在或无权访问")
        visible_observation(db,user,row.observation_id)
        return row
    def render(row):
        return {"id":row.id,"observation_id":row.observation_id,"status":row.status,"investigator_id":row.investigator_id,"last_submitter_id":row.last_submitter_id,"version":row.version,"created_at":row.created_at}
    def clean(text):
        result=text.strip()
        if not result:raise error(422,"VALIDATION_ERROR","说明不能为空")
        return result
    @router.get("/inventory-observations/{observation_id}/investigation")
    def detail(observation_id:str,request:Request,page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
        visible_observation(db,user,observation_id)
        investigation=db.scalar(select(InventoryInvestigation).where(InventoryInvestigation.observation_id==observation_id,InventoryInvestigation.org_id==user.org_id))
        events=[];total=0
        if investigation:
            stmt=select(InventoryInvestigationEvent).where(InventoryInvestigationEvent.investigation_id==investigation.id,InventoryInvestigationEvent.org_id==user.org_id)
            total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
            rows=db.scalars(stmt.order_by(InventoryInvestigationEvent.created_at.asc(),InventoryInvestigationEvent.id.asc()).offset((page-1)*page_size).limit(page_size)).all()
            events=[{"id":e.id,"actor_id":e.actor_id,"action":e.action,"before_status":e.before_status,"after_status":e.after_status,"note":e.note,"created_at":e.created_at} for e in rows]
        audit(db,user,"INVENTORY_INVESTIGATION_VIEW",observation_id);db.commit()
        return {"investigation":render(investigation) if investigation else None,"events":page_result(events,page,page_size,total,request_id(request))}
    @router.post("/inventory-observations/{observation_id}/investigation",status_code=201)
    def start(observation_id:str,data:StartInvestigation,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        observation=visible_observation(db,user,observation_id);note=clean(data.note)
        record,replay=reserve(db,user,"INVENTORY_INVESTIGATION_START",key,{"observation_id":observation_id,"note":note})
        if replay:return replay
        if observation.difference==0:raise error(409,"NO_DIFFERENCE","该盘点没有重量差异，无需创建差异调查")
        investigation=InventoryInvestigation(org_id=user.org_id,observation_id=observation.id,status="OPEN",investigator_id=user.id,version=1)
        db.add(investigation)
        try:db.flush()
        except IntegrityError:
            db.rollback();raise error(409,"INVESTIGATION_EXISTS","该盘点已有调查记录")
        db.add(InventoryInvestigationEvent(org_id=user.org_id,investigation_id=investigation.id,actor_id=user.id,action="START",after_status="OPEN",note=note))
        audit(db,user,"INVENTORY_INVESTIGATION_START",investigation.id);result=render(investigation);finish(record,result,201,investigation.id);db.commit();return result
    @router.post("/inventory-investigations/{investigation_id}/transition")
    def transition(investigation_id:str,data:InvestigationTransition,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        investigation=visible_investigation(db,user,investigation_id);note=clean(data.note)
        record,replay=reserve(db,user,"INVENTORY_INVESTIGATION_TRANSITION",key,{"investigation_id":investigation_id,"version":data.version,"action":data.action,"note":note})
        if replay:return replay
        if data.action=="SUBMIT":
            if investigation.investigator_id!=user.id:raise error(403,"FORBIDDEN","仅调查人可提交调查说明")
            allowed=("OPEN","RETURNED");target="PENDING_REVIEW"
            values={"status":target,"version":InventoryInvestigation.version+1,"last_submitter_id":user.id}
        else:
            if investigation.last_submitter_id is None or investigation.last_submitter_id==user.id:
                raise error(403,"FORBIDDEN","须由调查提交人以外的用户复核")
            allowed=("PENDING_REVIEW",);target="RETURNED" if data.action=="RETURN" else "REVIEWED"
            values={"status":target,"version":InventoryInvestigation.version+1}
        before=investigation.status
        changed=db.execute(update(InventoryInvestigation).where(InventoryInvestigation.id==investigation_id,InventoryInvestigation.org_id==user.org_id,InventoryInvestigation.version==data.version,InventoryInvestigation.status.in_(allowed)).values(**values))
        if changed.rowcount!=1:raise error(409,"VERSION_OR_STATE_CONFLICT","调查状态或版本已改变，请重新查看")
        db.refresh(investigation);db.add(InventoryInvestigationEvent(org_id=user.org_id,investigation_id=investigation.id,actor_id=user.id,action=data.action,before_status=before,after_status=target,note=note))
        audit(db,user,"INVENTORY_INVESTIGATION_"+data.action,investigation.id);result=render(investigation);finish(record,result,200,investigation.id);db.commit();return result
    return router
