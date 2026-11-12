"""未核验人员档案与案件的候选关系，不产生正式人员关联。"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Case, PersonDraft, PersonCaseCandidate, PersonCaseCandidateEvent, User
from .security import current_user
from .person_core import current_org
from .clue_deliveries import lock_flow

class CandidateCreate(BaseModel):
    case_id: str = Field(min_length=1,max_length=36)
    person_version: int = Field(ge=1)
    basis: str = Field(min_length=1,max_length=1000)

class CandidateRevoke(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1,max_length=1000)


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix="/api/person-drafts",tags=["人员案件候选关联（开发验证）"])
    def person_for(db,user,person_id):
        row=db.scalar(select(PersonDraft).where(PersonDraft.id==person_id,PersonDraft.org_id==user.org_id))
        if not row:raise error(404,"NOT_FOUND","记录不存在或无权访问")
        return row
    def case_for(db,user,case_id):
        row=db.scalar(select(Case).where(Case.id==case_id,Case.org_id==user.org_id))
        if not row:raise error(404,"NOT_FOUND","记录不存在或无权访问")
        return row
    def render(row,case):
        return {"id":row.id,"person_id":row.person_id,"case_id":case.id,"case_number":case.number,"case_title":case.title,"basis":row.basis,"status":row.status,"version":row.version,"created_by":row.created_by,"created_at":row.created_at,"revoked_by":row.revoked_by,"revoked_at":row.revoked_at,"revoke_reason":row.revoke_reason,"verification":"CANDIDATE"}
    @router.get("/{person_id}/case-candidates")
    def listing(person_id:str,request:Request,page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
        person_for(db,user,person_id)
        stmt=select(PersonCaseCandidate,Case).join(Case,Case.id==PersonCaseCandidate.case_id).where(PersonCaseCandidate.person_id==person_id,PersonCaseCandidate.org_id==user.org_id,Case.org_id==user.org_id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.execute(stmt.order_by(PersonCaseCandidate.created_at.desc(),PersonCaseCandidate.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        result=page_result([render(candidate,case) for candidate,case in rows],page,page_size,total,request_id(request))
        audit(db,user,"PERSON_CASE_CANDIDATES_VIEW",person_id);db.commit();return result
    @router.post("/{person_id}/case-candidates",status_code=201)
    def create(person_id:str,data:CandidateCreate,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        lock_flow(db,user,'persons.write',error,'persons.read')
        person=person_for(db,user,person_id);case=case_for(db,user,data.case_id);basis=data.basis.strip()
        if current_org(person)!=user.org_id:raise error(403,'FORBIDDEN','人员责任已移交，原单位候选记录只供历史查看')
        if not basis:raise error(422,"VALIDATION_ERROR","候选依据不能为空")
        body={"person_id":person_id,"case_id":case.id,"person_version":data.person_version,"basis":basis}
        record,replay=reserve(db,user,"PERSON_CASE_CANDIDATE_CREATE",key,body)
        if replay:return replay
        changed=db.execute(update(PersonDraft).where(PersonDraft.id==person.id,PersonDraft.org_id==user.org_id,PersonDraft.version==data.person_version).values(version=PersonDraft.version+1))
        if changed.rowcount!=1:raise error(409,"VERSION_CONFLICT","人员档案已变化，请重新查看")
        candidate=PersonCaseCandidate(org_id=user.org_id,person_id=person.id,case_id=case.id,basis=basis,status="ACTIVE",version=1,created_by=user.id)
        db.add(candidate)
        try:db.flush()
        except IntegrityError:
            db.rollback();raise error(409,"CANDIDATE_EXISTS","人员与案件已有有效候选关联")
        db.add(PersonCaseCandidateEvent(org_id=user.org_id,candidate_id=candidate.id,actor_id=user.id,action="CREATE",note=basis))
        audit(db,user,"PERSON_CASE_CANDIDATE_CREATE",candidate.id);result=render(candidate,case);finish(record,result,201,candidate.id);db.commit();return result
    @router.post("/case-candidates/{candidate_id}/revoke")
    def revoke(candidate_id:str,data:CandidateRevoke,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        lock_flow(db,user,'persons.write',error,'persons.read')
        candidate=db.scalar(select(PersonCaseCandidate).where(PersonCaseCandidate.id==candidate_id,PersonCaseCandidate.org_id==user.org_id))
        if not candidate:raise error(404,"NOT_FOUND","记录不存在或无权访问")
        person=person_for(db,user,candidate.person_id);case=case_for(db,user,candidate.case_id);reason=data.reason.strip()
        if current_org(person)!=user.org_id:raise error(403,'FORBIDDEN','人员责任已移交，原单位候选记录只供历史查看')
        if not reason:raise error(422,"VALIDATION_ERROR","撤销原因不能为空")
        record,replay=reserve(db,user,"PERSON_CASE_CANDIDATE_REVOKE",key,{"candidate_id":candidate_id,"version":data.version,"reason":reason})
        if replay:return replay
        changed=db.execute(update(PersonCaseCandidate).where(PersonCaseCandidate.id==candidate_id,PersonCaseCandidate.org_id==user.org_id,PersonCaseCandidate.status=="ACTIVE",PersonCaseCandidate.version==data.version).values(status="REVOKED",version=PersonCaseCandidate.version+1,revoked_by=user.id,revoked_at=datetime.now(timezone.utc),revoke_reason=reason))
        if changed.rowcount!=1:raise error(409,"VERSION_OR_STATE_CONFLICT","关联状态或版本已改变，请重新查看")
        db.refresh(candidate);db.add(PersonCaseCandidateEvent(org_id=user.org_id,candidate_id=candidate.id,actor_id=user.id,action="REVOKE",note=reason))
        audit(db,user,"PERSON_CASE_CANDIDATE_REVOKE",candidate.id);result=render(candidate,case);finish(record,result,200,candidate.id);db.commit();return result
    return router
