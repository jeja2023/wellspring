"""最小人员草稿，仅用于虚构数据验证。"""
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .db import get_db
from .models import PersonDraft, User
from .security import current_user

class PersonSearch(BaseModel):
    keyword: str = Field(default="",max_length=100)
    page: int = Field(default=1,ge=1,le=100000)
    page_size: int = Field(default=20,ge=1,le=100)

class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=200)


def create_router(error, audit, reserve, finish, page_result, request_id):
    router=APIRouter(prefix="/api/person-drafts",tags=["人员草稿（开发验证）"])
    def as_json(person):
        return {"id":person.id,"name":person.name,"source":person.source,
                "verification_status":person.verification_status,"version":person.version,"created_at":person.created_at}

    @router.get("")
    def list_people(request: Request, page: int=Query(1,ge=1,le=100000), page_size: int=Query(20,ge=1,le=100), user: User=Depends(current_user), db: Session=Depends(get_db)):
        stmt=select(PersonDraft).where(PersonDraft.org_id==user.org_id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.scalars(stmt.order_by(PersonDraft.created_at.desc(),PersonDraft.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        audit(db,user,"PERSON_DRAFT_LIST",user.org_id);db.commit()
        return page_result([as_json(row) for row in rows],page,page_size,total,request_id(request))

    @router.post("/search")
    def search_people(data:PersonSearch,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
        stmt=select(PersonDraft).where(PersonDraft.org_id==user.org_id)
        if data.keyword.strip():
            term=data.keyword.strip()
            stmt=stmt.where((PersonDraft.name.contains(term,autoescape=True)) | (PersonDraft.source.contains(term,autoescape=True)))
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.scalars(stmt.order_by(PersonDraft.created_at.desc(),PersonDraft.id.desc()).offset((data.page-1)*data.page_size).limit(data.page_size)).all()
        audit(db,user,"PERSON_DRAFT_SEARCH",user.org_id);db.commit()
        return page_result([as_json(row) for row in rows],data.page,data.page_size,total,request_id(request))

    @router.post("",status_code=201)
    def create_person(data:PersonCreate,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        name,source=data.name.strip(),data.source.strip()
        if not name or not source: raise error(422,"VALIDATION_ERROR","名称和来源不能为空")
        record,replay=reserve(db,user,"PERSON_DRAFT_CREATE",key,{"name":name,"source":source})
        if replay:return replay
        person=PersonDraft(org_id=user.org_id,name=name,source=source,verification_status="UNVERIFIED",version=1,created_by=user.id)
        db.add(person);db.flush();audit(db,user,"PERSON_DRAFT_CREATE",person.id)
        result=as_json(person);finish(record,result,201,person.id);db.commit();return result
    return router
