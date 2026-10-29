"""开发验证用的线索与案件关联，需同时校验两端可见范围。"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Case, Clue, ClueCaseLink, IntelligenceEvent, User
from .security import current_user

class LinkCreate(BaseModel):
    case_id: str = Field(min_length=1, max_length=36)
    clue_version: int = Field(ge=1)
    basis: str = Field(min_length=1, max_length=1000)

class LinkRevoke(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


def create_router(error, audit, reserve, finish, page_result, request_id):
    router = APIRouter(prefix="/api/intelligence", tags=["情报线索关联（开发验证）"])

    def require_clue(db, user, clue_id):
        clue = db.scalar(select(Clue).where(Clue.id == clue_id, Clue.org_id == user.org_id))
        if not clue: raise error(404, "NOT_FOUND", "记录不存在或无权访问")
        return clue

    def require_case(db, user, case_id):
        case = db.scalar(select(Case).where(Case.id == case_id, Case.org_id == user.org_id))
        if not case: raise error(404, "NOT_FOUND", "记录不存在或无权访问")
        return case

    def link_json(link, case):
        return {"id":link.id,"clue_id":link.clue_id,"case_id":case.id,"case_number":case.number,
                "case_title":case.title,"basis":link.basis,"status":link.status,"version":link.version,
                "created_by":link.created_by,"created_at":link.created_at,"revoked_by":link.revoked_by,
                "revoked_at":link.revoked_at,"revoke_reason":link.revoke_reason}

    @router.get("/clues/{clue_id}/case-links")
    def list_links(clue_id: str, request: Request, page: int = Query(1,ge=1,le=100000), page_size: int = Query(20,ge=1,le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_clue(db,user,clue_id)
        stmt = select(ClueCaseLink, Case).join(Case, Case.id == ClueCaseLink.case_id).where(
            ClueCaseLink.clue_id == clue_id, ClueCaseLink.org_id == user.org_id, Case.org_id == user.org_id)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(stmt.order_by(ClueCaseLink.created_at.desc(), ClueCaseLink.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        result = page_result([link_json(link, case) for link, case in rows], page, page_size, total, request_id(request))
        audit(db,user,"CLUE_CASE_LINKS_VIEW",clue_id); db.commit()
        return result

    @router.post("/clues/{clue_id}/case-links", status_code=201)
    def create_link(clue_id: str, data: LinkCreate, key: str | None = Header(None,alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        clue = require_clue(db,user,clue_id)
        case = require_case(db,user,data.case_id)
        basis = data.basis.strip()
        if not basis: raise error(422,"VALIDATION_ERROR","关联依据不能为空")
        record,replay = reserve(db,user,"CLUE_CASE_LINK_CREATE",key,{"clue_id":clue_id,"case_id":case.id,"clue_version":data.clue_version,"basis":basis})
        if replay: return replay
        changed = db.execute(update(Clue).where(Clue.id == clue_id, Clue.org_id == user.org_id,
                             Clue.status == "REVIEWED", Clue.version == data.clue_version).values(version=Clue.version+1))
        if changed.rowcount != 1: raise error(409,"VERSION_OR_STATE_CONFLICT","请先核验线索并重新获取最新版本")
        link = ClueCaseLink(org_id=user.org_id, clue_id=clue.id, case_id=case.id, basis=basis, status="ACTIVE", created_by=user.id, version=1)
        db.add(link)
        try: db.flush()
        except IntegrityError:
            db.rollback(); raise error(409,"LINK_EXISTS","该线索和案件已有有效关联")
        db.add(IntelligenceEvent(org_id=user.org_id,clue_id=clue.id,task_id=None,related_link_id=link.id,actor_id=user.id,action="CASE_LINKED",before_status="REVIEWED",after_status="REVIEWED",note="已记录案件关联"))
        audit(db,user,"CLUE_CASE_LINK_CREATE",link.id)
        result=link_json(link,case);finish(record,result,201,link.id);db.commit();return result

    @router.post("/case-links/{link_id}/revoke")
    def revoke_link(link_id: str, data: LinkRevoke, key: str | None = Header(None,alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        link = db.scalar(select(ClueCaseLink).where(ClueCaseLink.id==link_id,ClueCaseLink.org_id==user.org_id))
        if not link: raise error(404,"NOT_FOUND","记录不存在或无权访问")
        require_clue(db,user,link.clue_id)
        case = require_case(db,user,link.case_id)
        reason = data.reason.strip()
        if not reason: raise error(422,"VALIDATION_ERROR","撤销原因不能为空")
        record,replay=reserve(db,user,"CLUE_CASE_LINK_REVOKE",key,{"link_id":link_id,"version":data.version,"reason":reason})
        if replay: return replay
        changed=db.execute(update(ClueCaseLink).where(ClueCaseLink.id==link_id,ClueCaseLink.org_id==user.org_id,ClueCaseLink.status=="ACTIVE",ClueCaseLink.version==data.version).values(status="REVOKED",version=ClueCaseLink.version+1,revoked_by=user.id,revoked_at=datetime.now(timezone.utc),revoke_reason=reason))
        if changed.rowcount != 1: raise error(409,"VERSION_OR_STATE_CONFLICT","关联状态或版本已改变，请重新查看")
        db.refresh(link)
        db.add(IntelligenceEvent(org_id=user.org_id,clue_id=link.clue_id,task_id=None,related_link_id=link.id,actor_id=user.id,action="CASE_LINK_REVOKED",before_status="REVIEWED",after_status="REVIEWED",note="已撤销案件关联"))
        audit(db,user,"CLUE_CASE_LINK_REVOKE",link.id)
        result=link_json(link,case);finish(record,result,200,link.id);db.commit();return result
    return router
