"""同组织案件关联和协办的开发验证；不执行并案。"""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased
from .db import get_db
from .models import Case, CaseRelation, CaseRelationEvent, User
from .security import current_user

class RelationCreate(BaseModel):
    target_case_id: str = Field(min_length=1,max_length=36)
    relation_type: Literal["RELATED_TO","COOPERATE_WITH"]
    basis: str = Field(min_length=1,max_length=1000)

class RelationRevoke(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1,max_length=1000)


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix="/api/cases",tags=["案件关系（开发验证）"])
    def visible(db,user,case_id):
        row=db.scalar(select(Case).where(Case.id==case_id,Case.org_id==user.org_id))
        if not row:raise error(404,"NOT_FOUND","记录不存在或无权访问")
        return row
    def render(rel,other):
        return {"id":rel.id,"other_case_id":other.id,"other_case_number":other.number,"other_case_title":other.title,"relation_type":rel.relation_type,"relation_status":rel.relation_status,"basis":rel.basis,"version":rel.version,"created_by":rel.created_by,"created_at":rel.created_at,"revoked_by":rel.revoked_by,"revoked_at":rel.revoked_at,"revoke_reason":rel.revoke_reason}
    @router.get("/{case_id}/relations")
    def listing(case_id:str,request:Request,page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
        visible(db,user,case_id)
        other=aliased(Case)
        stmt=select(CaseRelation,other).join(other,or_((CaseRelation.source_case_id==case_id)&(other.id==CaseRelation.target_case_id),(CaseRelation.target_case_id==case_id)&(other.id==CaseRelation.source_case_id))).where(CaseRelation.org_id==user.org_id,other.org_id==user.org_id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.execute(stmt.order_by(CaseRelation.created_at.desc(),CaseRelation.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        data=page_result([render(rel,case) for rel,case in rows],page,page_size,total,request_id(request))
        audit(db,user,"CASE_RELATIONS_VIEW",case_id);db.commit();return data
    @router.post("/{case_id}/relations",status_code=201)
    def create(case_id:str,data:RelationCreate,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        visible(db,user,case_id);other=visible(db,user,data.target_case_id)
        if case_id==data.target_case_id:raise error(422,"VALIDATION_ERROR","不能关联同一个案件")
        basis=data.basis.strip()
        if not basis:raise error(422,"VALIDATION_ERROR","关联依据不能为空")
        source,target=sorted((case_id,data.target_case_id))
        body={"source_case_id":source,"target_case_id":target,"relation_type":data.relation_type,"basis":basis,"requested_case_id":case_id}
        record,replay=reserve(db,user,"CASE_RELATION_CREATE",key,body)
        if replay:return replay
        rel=CaseRelation(org_id=user.org_id,source_case_id=source,target_case_id=target,relation_type=data.relation_type,relation_status="ACTIVE",basis=basis,version=1,created_by=user.id)
        db.add(rel)
        try:db.flush()
        except IntegrityError:
            db.rollback();raise error(409,"RELATION_EXISTS","这两个案件已有相同类型的有效关系")
        db.add(CaseRelationEvent(org_id=user.org_id,relation_id=rel.id,actor_id=user.id,action="CREATE",after_status="ACTIVE",note=basis))
        audit(db,user,"CASE_RELATION_CREATE",rel.id);result=render(rel,other);finish(record,result,201,rel.id);db.commit();return result
    @router.post("/relations/{relation_id}/revoke")
    def revoke(relation_id:str,data:RelationRevoke,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        rel=db.scalar(select(CaseRelation).where(CaseRelation.id==relation_id,CaseRelation.org_id==user.org_id))
        if not rel:raise error(404,"NOT_FOUND","记录不存在或无权访问")
        visible(db,user,rel.source_case_id);other=visible(db,user,rel.target_case_id)
        reason=data.reason.strip()
        if not reason:raise error(422,"VALIDATION_ERROR","撤销原因不能为空")
        record,replay=reserve(db,user,"CASE_RELATION_REVOKE",key,{"relation_id":relation_id,"version":data.version,"reason":reason})
        if replay:return replay
        changed=db.execute(update(CaseRelation).where(CaseRelation.id==relation_id,CaseRelation.org_id==user.org_id,CaseRelation.version==data.version,CaseRelation.relation_status=="ACTIVE").values(relation_status="REVOKED",version=CaseRelation.version+1,revoked_by=user.id,revoked_at=datetime.now(timezone.utc),revoke_reason=reason))
        if changed.rowcount!=1:raise error(409,"VERSION_OR_STATE_CONFLICT","关系状态或版本已变化，请重新查看")
        db.refresh(rel);db.add(CaseRelationEvent(org_id=user.org_id,relation_id=rel.id,actor_id=user.id,action="REVOKE",before_status="ACTIVE",after_status="REVOKED",note=reason))
        audit(db,user,"CASE_RELATION_REVOKE",rel.id);result=render(rel,other);finish(record,result,200,rel.id);db.commit();return result
    return router
