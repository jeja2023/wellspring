"""证物保管及交接开发验证；不是实物交接或正式审批。"""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import CustodyEvent, CustodyHandover, Evidence, EvidenceCustody, User
from .security import current_user

class BaselineInput(BaseModel):
    evidence_version: int = Field(ge=1)
    note: str = Field(min_length=1,max_length=1000)

class HandoverInput(BaseModel):
    custody_version: int = Field(ge=1)
    to_user_id: str = Field(min_length=1,max_length=36)
    note: str = Field(min_length=1,max_length=1000)

class HandoverResponse(BaseModel):
    version: int = Field(ge=1)
    action: Literal["ACCEPT","REJECT"]
    note: str = Field(min_length=1,max_length=1000)


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix="/api/evidence",tags=["证物交接（开发验证）"])
    def evidence_for(db,user,evidence_id):
        item=db.scalar(select(Evidence).where(Evidence.id==evidence_id,Evidence.org_id==user.org_id))
        if not item:raise error(404,"NOT_FOUND","记录不存在或无权访问")
        return item
    def custody_for(db,user,evidence_id):
        row=db.scalar(select(EvidenceCustody).where(EvidenceCustody.evidence_id==evidence_id,EvidenceCustody.org_id==user.org_id))
        if not row:raise error(409,"CUSTODY_UNINITIALIZED","该证物尚未登记开发保管基线")
        return row
    def clean(value):
        value=value.strip()
        if not value:raise error(422,"VALIDATION_ERROR","说明不能为空")
        return value
    def event(db,user,evidence_id,handover_id,action,note):
        db.add(CustodyEvent(org_id=user.org_id,evidence_id=evidence_id,handover_id=handover_id,actor_id=user.id,action=action,note=note))
    def custody_json(row):return {"id":row.id,"evidence_id":row.evidence_id,"custodian_id":row.custodian_id,"version":row.version}
    def handover_json(row):return {"id":row.id,"evidence_id":row.evidence_id,"from_user_id":row.from_user_id,"to_user_id":row.to_user_id,"status":row.status,"version":row.version,"note":row.note,"response_note":row.response_note,"created_at":row.created_at,"responded_at":row.responded_at}
    @router.get("/{evidence_id}/custody")
    def get_custody(evidence_id:str,request:Request,page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
        evidence_for(db,user,evidence_id)
        custody=db.scalar(select(EvidenceCustody).where(EvidenceCustody.evidence_id==evidence_id,EvidenceCustody.org_id==user.org_id))
        pending=db.scalar(select(CustodyHandover).where(CustodyHandover.evidence_id==evidence_id,CustodyHandover.org_id==user.org_id,CustodyHandover.status=="PENDING"))
        stmt=select(CustodyEvent).where(CustodyEvent.evidence_id==evidence_id,CustodyEvent.org_id==user.org_id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.scalars(stmt.order_by(CustodyEvent.created_at.desc(),CustodyEvent.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        events=[{"id":row.id,"handover_id":row.handover_id,"actor_id":row.actor_id,"action":row.action,"note":row.note,"created_at":row.created_at} for row in rows]
        audit(db,user,"EVIDENCE_CUSTODY_VIEW",evidence_id);db.commit()
        return {"current_user_id":user.id,"custody":custody_json(custody) if custody else None,"pending":handover_json(pending) if pending else None,"events":page_result(events,page,page_size,total,request_id(request))}
    @router.get("/{evidence_id}/handovers")
    def list_handovers(evidence_id:str,request:Request,page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
        evidence_for(db,user,evidence_id)
        stmt=select(CustodyHandover).where(CustodyHandover.evidence_id==evidence_id,CustodyHandover.org_id==user.org_id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.scalars(stmt.order_by(CustodyHandover.created_at.desc(),CustodyHandover.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        result=page_result([handover_json(row) for row in rows],page,page_size,total,request_id(request))
        audit(db,user,"CUSTODY_HANDOVER_LIST",evidence_id);db.commit();return result
    @router.post("/{evidence_id}/custody/baseline",status_code=201)
    def baseline(evidence_id:str,data:BaselineInput,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        evidence_for(db,user,evidence_id);note=clean(data.note)
        record,replay=reserve(db,user,"CUSTODY_BASELINE",key,{"evidence_id":evidence_id,"evidence_version":data.evidence_version,"note":note})
        if replay:return replay
        if db.scalar(select(EvidenceCustody.id).where(EvidenceCustody.evidence_id==evidence_id)):
            raise error(409,"CUSTODY_EXISTS","保管基线已存在")
        changed=db.execute(update(Evidence).where(Evidence.id==evidence_id,Evidence.org_id==user.org_id,Evidence.version==data.evidence_version).values(version=Evidence.version+1))
        if changed.rowcount!=1:raise error(409,"VERSION_CONFLICT","证物已变化，请重新查看")
        row=EvidenceCustody(org_id=user.org_id,evidence_id=evidence_id,custodian_id=user.id,version=1);db.add(row)
        try:db.flush()
        except IntegrityError:
            db.rollback();raise error(409,"CUSTODY_EXISTS","保管基线已存在")
        event(db,user,evidence_id,None,"BASELINE",note);audit(db,user,"CUSTODY_BASELINE",row.id)
        result=custody_json(row);finish(record,result,201,row.id);db.commit();return result
    @router.post("/{evidence_id}/handovers",status_code=201)
    def handover(evidence_id:str,data:HandoverInput,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        evidence_for(db,user,evidence_id);custody=custody_for(db,user,evidence_id);note=clean(data.note)
        target=db.scalar(select(User).where(User.id==data.to_user_id,User.org_id==user.org_id,User.active.is_(True)))
        if not target:raise error(404,"NOT_FOUND","接收人不存在或无权访问")
        record,replay=reserve(db,user,"CUSTODY_HANDOVER_CREATE",key,{"evidence_id":evidence_id,"custody_version":data.custody_version,"to_user_id":target.id,"note":note})
        if replay:return replay
        if user.id!=custody.custodian_id:raise error(403,"FORBIDDEN","只有当前保管人可发起交接")
        if target.id==user.id:raise error(422,"VALIDATION_ERROR","交出人与接收人不能相同")
        changed=db.execute(update(EvidenceCustody).where(EvidenceCustody.id==custody.id,EvidenceCustody.org_id==user.org_id,EvidenceCustody.custodian_id==user.id,EvidenceCustody.version==data.custody_version).values(version=EvidenceCustody.version+1))
        if changed.rowcount!=1:raise error(409,"VERSION_CONFLICT","保管信息已变化，请重新查看")
        row=CustodyHandover(org_id=user.org_id,evidence_id=evidence_id,from_user_id=user.id,to_user_id=target.id,custody_version=data.custody_version+1,status="PENDING",version=1,note=note);db.add(row)
        try:db.flush()
        except IntegrityError:
            db.rollback();raise error(409,"HANDOVER_PENDING","该证物已有待接收交接")
        event(db,user,evidence_id,row.id,"HANDOVER_PROPOSED",note);audit(db,user,"CUSTODY_HANDOVER_CREATE",row.id)
        result=handover_json(row);finish(record,result,201,row.id);db.commit();return result
    @router.post("/handovers/{handover_id}/respond")
    def respond(handover_id:str,data:HandoverResponse,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        handover=db.scalar(select(CustodyHandover).where(CustodyHandover.id==handover_id,CustodyHandover.org_id==user.org_id))
        if not handover:raise error(404,"NOT_FOUND","记录不存在或无权访问")
        evidence_for(db,user,handover.evidence_id);custody=custody_for(db,user,handover.evidence_id);note=clean(data.note)
        if handover.to_user_id!=user.id:raise error(403,"FORBIDDEN","只有指定接收人可确认或拒收")
        record,replay=reserve(db,user,"CUSTODY_HANDOVER_RESPONSE",key,{"handover_id":handover_id,"version":data.version,"action":data.action,"note":note})
        if replay:return replay
        new_status="ACCEPTED" if data.action=="ACCEPT" else "REJECTED"
        changed=db.execute(update(CustodyHandover).where(CustodyHandover.id==handover_id,CustodyHandover.org_id==user.org_id,CustodyHandover.to_user_id==user.id,CustodyHandover.status=="PENDING",CustodyHandover.version==data.version).values(status=new_status,version=CustodyHandover.version+1,response_note=note,responded_at=datetime.now(timezone.utc)))
        if changed.rowcount!=1:raise error(409,"VERSION_OR_STATE_CONFLICT","交接状态或版本已变化，请重新查看")
        custody_changed=db.execute(update(EvidenceCustody).where(EvidenceCustody.id==custody.id,EvidenceCustody.org_id==user.org_id,EvidenceCustody.custodian_id==handover.from_user_id,EvidenceCustody.version==handover.custody_version).values(custodian_id=user.id if data.action=="ACCEPT" else handover.from_user_id,version=EvidenceCustody.version+1))
        if custody_changed.rowcount!=1:raise error(409,"VERSION_CONFLICT","保管信息已变化，请重新查看")
        db.refresh(handover);event(db,user,handover.evidence_id,handover.id,"HANDOVER_"+new_status,note);audit(db,user,"CUSTODY_HANDOVER_"+new_status,handover.id)
        result=handover_json(handover);finish(record,result,200,handover.id);db.commit();return result
    return router
