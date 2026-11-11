"""开发验证用线索及核查工单路由。不可用于真实业务。"""
import re
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Clue, InvestigationTask, IntelligenceEvent, User
from uuid import uuid4
from .security import current_user

class ClueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=10000)
    source: str = Field(min_length=1, max_length=200)
    reference_no:str|None=Field(default=None,min_length=1,max_length=80)
    priority:Literal['NORMAL','IMPORTANT']='NORMAL'
    suggested_due_date:date|None=None

class ClueSearch(BaseModel):
    keyword: str = Field(default="", max_length=100)
    status: Literal["DRAFT", "REVIEWED"] | None = None
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=20, ge=1, le=100)

class ReviewClue(BaseModel):
    version: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=1000)

class TaskCreate(BaseModel):
    clue_version: int = Field(ge=1)
    objective: str = Field(min_length=1, max_length=1000)
    assignee_id: str = Field(min_length=1, max_length=36)
    due_date: date | None = None

    @field_validator("due_date", mode="before")
    @classmethod
    def require_date_string(cls, value):
        if value is None:
            return value
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("日期须使用 YYYY-MM-DD 格式")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("日期须使用 YYYY-MM-DD 格式") from exc

class TaskReassign(BaseModel):
    version: int = Field(ge=1)
    assignee_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=1, max_length=1000)

class TaskTransition(BaseModel):
    version: int = Field(ge=1)
    action: Literal["SUBMIT", "RETURN", "CLOSE"]
    note: str = Field(min_length=1, max_length=1000)
    result: Literal["VERIFIED", "NO_FINDING", "INSUFFICIENT", "DUPLICATE", "TRANSFER", "CONTINUE"] | None = None


def create_router(error, audit, reserve, finish, page_result, request_id):
    router = APIRouter(prefix="/api/intelligence", tags=["情报线索（开发验证）"])

    def visible_clue(db, user, clue_id):
        clue = db.scalar(select(Clue).where(Clue.id == clue_id, Clue.org_id == user.org_id))
        if not clue:
            raise error(404, "NOT_FOUND", "记录不存在或无权访问")
        return clue

    def visible_task(db, user, task_id):
        task = db.scalar(select(InvestigationTask).where(InvestigationTask.id == task_id, InvestigationTask.org_id == user.org_id))
        if not task:
            raise error(404, "NOT_FOUND", "记录不存在或无权访问")
        visible_clue(db, user, task.clue_id)
        return task

    def clean(value):
        value = value.strip()
        if not value:
            raise error(422, "VALIDATION_ERROR", "必填内容不能为空")
        return value

    def clue_json(c):
        return {"id":c.id,"title":c.title,"summary":c.summary,"source":c.source,"status":c.status,"created_by":c.created_by,"version":c.version,"created_at":c.created_at,
            "reference_no":c.reference_no,"priority":c.priority,"suggested_due_date":c.suggested_due_date}

    def task_json(t):
        return {"id":t.id,"clue_id":t.clue_id,"objective":t.objective,"assignee_id":t.assignee_id,"due_date":t.due_date,"status":t.status,"result":t.result_code,"version":t.version,"created_at":t.created_at}

    def event(db, user, clue_id, task_id, action, before, after, note, result_code=None, assignee_after_id=None):
        db.add(IntelligenceEvent(org_id=user.org_id, clue_id=clue_id, task_id=task_id, actor_id=user.id, action=action, before_status=before, after_status=after, note=note, result_code=result_code, assignee_after_id=assignee_after_id))

    @router.get("/assignees")
    def assignees(user: User = Depends(current_user), db: Session = Depends(get_db)):
        rows = db.scalars(select(User).where(User.org_id == user.org_id, User.active == True).order_by(User.username).limit(100)).all()
        audit(db, user, "INTELLIGENCE_ASSIGNEES_VIEW", user.org_id)
        db.commit()
        return [{"id":u.id,"username":u.username} for u in rows]

    @router.get("/clues")
    def list_clues(request: Request, page: int = Query(1,ge=1,le=100000), page_size: int = Query(20,ge=1,le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        stmt = select(Clue).where(Clue.org_id == user.org_id)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.order_by(Clue.created_at.desc(),Clue.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        audit(db,user,"CLUE_LIST",user.org_id); db.commit()
        return page_result([clue_json(c) for c in rows],page,page_size,total,request_id(request))

    @router.post("/clues/search")
    def search_clues(data: ClueSearch, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
        # 搜索内容不进入 URL 或审计日志；先限制组织再筛选与分页。
        stmt = select(Clue).where(Clue.org_id == user.org_id)
        if data.keyword.strip():
            term = data.keyword.strip()
            stmt = stmt.where((Clue.title.contains(term, autoescape=True)) | (Clue.source.contains(term, autoescape=True)))
        if data.status is not None:
            stmt = stmt.where(Clue.status == data.status)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.order_by(Clue.created_at.desc(), Clue.id.desc()).offset((data.page-1)*data.page_size).limit(data.page_size)).all()
        audit(db,user,"CLUE_SEARCH",user.org_id); db.commit()
        return page_result([clue_json(c) for c in rows],data.page,data.page_size,total,request_id(request))

    @router.get("/tasks/mine")
    def my_tasks(request: Request, page: int = Query(1,ge=1,le=100000), page_size: int = Query(20,ge=1,le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        stmt = select(InvestigationTask, Clue.title).join(Clue, Clue.id == InvestigationTask.clue_id).where(
            InvestigationTask.org_id == user.org_id, Clue.org_id == user.org_id,
            InvestigationTask.assignee_id == user.id, InvestigationTask.status != "CLOSED")
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(stmt.order_by(case((InvestigationTask.due_date.is_(None), 1), else_=0), InvestigationTask.due_date.asc(), InvestigationTask.id.asc()).offset((page-1)*page_size).limit(page_size)).all()
        items = [{**task_json(task), "clue_title": title} for task, title in rows]
        audit(db, user, "INVESTIGATION_MY_TASKS_VIEW", user.id); db.commit()
        return page_result(items,page,page_size,total,request_id(request))

    @router.get("/tasks/reviewable")
    def reviewable_tasks(request: Request, page: int = Query(1,ge=1,le=100000), page_size: int = Query(20,ge=1,le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        # 仅列出当前组织且提交人可确定、不是当前用户的待复核工单。
        stmt = select(InvestigationTask, Clue.title).join(Clue, Clue.id == InvestigationTask.clue_id).where(
            InvestigationTask.org_id == user.org_id, Clue.org_id == user.org_id,
            InvestigationTask.status == "PENDING_REVIEW", InvestigationTask.last_submitter_id.is_not(None),
            InvestigationTask.last_submitter_id != user.id)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(stmt.order_by(InvestigationTask.created_at.asc(), InvestigationTask.id.asc()).offset((page-1)*page_size).limit(page_size)).all()
        # 只返回定位线索所需的最小字段；详情仍需重新授权。
        items = [{"id":task.id,"clue_id":task.clue_id,"clue_title":title,"status":task.status} for task,title in rows]
        audit(db,user,"INVESTIGATION_REVIEW_QUEUE_VIEW",user.id); db.commit()
        return page_result(items,page,page_size,total,request_id(request))

    @router.post("/clues", status_code=201)
    def create_clue(data: ClueCreate, key: str | None = Header(None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        payload = {"title":clean(data.title),"summary":clean(data.summary),"source":clean(data.source)}
        record,replay = reserve(db,user,"CLUE_CREATE",key,{**payload,"reference_no":data.reference_no,"priority":data.priority,"suggested_due_date":data.suggested_due_date})
        if replay: return replay
        number=data.reference_no.strip() if data.reference_no else 'QB-'+uuid4().hex[:16].upper()
        if not number:raise error(422,'VALIDATION_ERROR','线索编号不能只包含空格')
        if db.scalar(select(Clue.id).where(Clue.org_id==user.org_id,Clue.reference_no==number)):raise error(409,'CLUE_NUMBER_EXISTS','本组织线索编号已存在')
        clue=Clue(org_id=user.org_id,created_by=user.id,status="DRAFT",version=1,reference_no=number,priority=data.priority,suggested_due_date=data.suggested_due_date,**payload)
        db.add(clue); db.flush()
        event(db,user,clue.id,None,"CREATED",None,"DRAFT","线索草稿已创建")
        audit(db,user,"CLUE_CREATE",clue.id)
        result=clue_json(clue); finish(record,result,201,clue.id); db.commit()
        return result

    @router.post("/clues/{clue_id}/review")
    def review_clue(clue_id: str, data: ReviewClue, key: str | None = Header(None,alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        clue=visible_clue(db,user,clue_id); note=clean(data.note)
        record,replay=reserve(db,user,"CLUE_REVIEW",key,{"clue_id":clue_id,"version":data.version,"note":note})
        if replay: return replay
        changed=db.execute(update(Clue).where(Clue.id==clue_id,Clue.org_id==user.org_id,Clue.version==data.version,Clue.status=="DRAFT").values(status="REVIEWED",version=Clue.version+1))
        if changed.rowcount != 1: raise error(409,"VERSION_OR_STATE_CONFLICT","线索状态或版本已改变，请重新查看")
        db.refresh(clue); event(db,user,clue.id,None,"REVIEWED","DRAFT","REVIEWED",note); audit(db,user,"CLUE_REVIEW",clue.id)
        result=clue_json(clue); finish(record,result,200,clue.id); db.commit(); return result

    @router.post("/clues/{clue_id}/tasks", status_code=201)
    def create_task(clue_id: str, data: TaskCreate, key: str | None = Header(None,alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        clue=visible_clue(db,user,clue_id); objective=clean(data.objective)
        assignee=db.scalar(select(User).where(User.id==data.assignee_id,User.org_id==user.org_id,User.active==True))
        if not assignee: raise error(404,"NOT_FOUND","承办人不存在或无权访问")
        body={"clue_id":clue_id,"clue_version":data.clue_version,"objective":objective,"assignee_id":data.assignee_id,"due_date":data.due_date.isoformat() if data.due_date else None}
        record,replay=reserve(db,user,"INVESTIGATION_CREATE",key,body)
        if replay: return replay
        # 条件更新同时锁定线索版本，避免并发创建工单与核验状态变更交错。
        changed=db.execute(update(Clue).where(Clue.id==clue_id,Clue.org_id==user.org_id,Clue.version==data.clue_version,Clue.status=="REVIEWED").values(version=Clue.version+1))
        if changed.rowcount != 1: raise error(409,"VERSION_OR_STATE_CONFLICT","请先核验线索并重新获取最新版本")
        task=InvestigationTask(org_id=user.org_id,clue_id=clue_id,objective=objective,due_date=data.due_date,assignee_id=assignee.id,status="OPEN",version=1)
        db.add(task)
        try: db.flush()
        except IntegrityError:
            db.rollback(); raise error(409,"TASK_EXISTS","该线索已有核查工单")
        event(db,user,clue_id,task.id,"TASK_CREATED",None,"OPEN",f"核查工单已创建；办理期限：{data.due_date.isoformat() if data.due_date else '未设置'}",assignee_after_id=task.assignee_id)
        audit(db,user,"INVESTIGATION_CREATE",task.id)
        result=task_json(task); finish(record,result,201,task.id); db.commit(); return result

    @router.get("/clues/{clue_id}/detail")
    def detail(clue_id: str, request: Request, page: int = Query(1,ge=1,le=100000), page_size: int = Query(20,ge=1,le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        clue=visible_clue(db,user,clue_id)
        task=db.scalar(select(InvestigationTask).where(InvestigationTask.clue_id==clue_id,InvestigationTask.org_id==user.org_id))
        stmt=select(IntelligenceEvent).where(IntelligenceEvent.clue_id==clue_id,IntelligenceEvent.org_id==user.org_id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.scalars(stmt.order_by(IntelligenceEvent.created_at.asc(),IntelligenceEvent.id.asc()).offset((page-1)*page_size).limit(page_size)).all()
        events=[{"id":e.id,"action":e.action,"related_link_id":e.related_link_id,"before_status":e.before_status,"after_status":e.after_status,"note":e.note,"result":e.result_code,"assignee_before_id":e.assignee_before_id,"assignee_after_id":e.assignee_after_id,"actor_id":e.actor_id,"created_at":e.created_at} for e in rows]
        audit(db,user,"CLUE_DETAIL_VIEW",clue_id); db.commit()
        return {"clue":clue_json(clue),"task":task_json(task) if task else None,"events":page_result(events,page,page_size,total,request_id(request))}

    @router.post("/tasks/{task_id}/reassign")
    def reassign(task_id: str, data: TaskReassign, key: str | None = Header(None,alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        task = visible_task(db,user,task_id)
        reason = clean(data.reason)
        target = db.scalar(select(User).where(User.id == data.assignee_id, User.org_id == user.org_id, User.active.is_(True)))
        if not target: raise error(404,"NOT_FOUND","承办人不存在或无权访问")
        body = {"task_id":task_id,"version":data.version,"assignee_id":target.id,"reason":reason}
        record,replay = reserve(db,user,"INVESTIGATION_REASSIGN",key,body)
        if replay: return replay
        if target.id == task.assignee_id: raise error(409,"SAME_ASSIGNEE","新承办人与当前承办人相同")
        previous = task.assignee_id
        previous_status = task.status
        changed = db.execute(update(InvestigationTask).where(
            InvestigationTask.id == task_id, InvestigationTask.org_id == user.org_id,
            InvestigationTask.version == data.version, InvestigationTask.assignee_id == previous,
            InvestigationTask.status.in_(("OPEN","RETURNED")),
        ).values(assignee_id=target.id, version=InvestigationTask.version+1))
        if changed.rowcount != 1: raise error(409,"VERSION_OR_STATE_CONFLICT","工单状态或版本已改变，或当前状态不允许重分派")
        db.refresh(task)
        db.add(IntelligenceEvent(org_id=user.org_id,clue_id=task.clue_id,task_id=task.id,
                                 actor_id=user.id,action="REASSIGN",before_status=previous_status,
                                 after_status=task.status,note=reason,assignee_before_id=previous,
                                 assignee_after_id=target.id))
        audit(db,user,"INVESTIGATION_REASSIGN",task.id)
        result = task_json(task);finish(record,result,200,task.id);db.commit();return result

    @router.post("/tasks/{task_id}/transition")
    def transition(task_id: str, data: TaskTransition, key: str | None = Header(None,alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        task=visible_task(db,user,task_id); note=clean(data.note)
        record,replay=reserve(db,user,"INVESTIGATION_TRANSITION",key,{"task_id":task_id,"version":data.version,"action":data.action,"note":note,"result":data.result})
        if replay: return replay
        if data.action=="SUBMIT":
            if task.assignee_id != user.id: raise error(403,"FORBIDDEN","仅承办人可以提交核查")
            if data.result is None: raise error(422,"VALIDATION_ERROR","提交核查时请选择结果")
            allowed=("OPEN","RETURNED"); target="PENDING_REVIEW"
            values={"status":target,"version":InvestigationTask.version+1,"last_submitter_id":user.id,"result_code":data.result}
        else:
            if data.result is not None: raise error(422,"VALIDATION_ERROR","复核操作不接受新的核查结果")
            if task.last_submitter_id is None or task.last_submitter_id == user.id: raise error(403,"FORBIDDEN","核查提交人不能复核自己的结果")
            allowed=("PENDING_REVIEW",); target="RETURNED" if data.action=="RETURN" else "CLOSED"
            values={"status":target,"version":InvestigationTask.version+1}
        before=task.status
        changed=db.execute(update(InvestigationTask).where(InvestigationTask.id==task_id,InvestigationTask.org_id==user.org_id,InvestigationTask.version==data.version,InvestigationTask.status.in_(allowed)).values(**values))
        if changed.rowcount != 1: raise error(409,"VERSION_OR_STATE_CONFLICT","工单状态或版本已改变，请重新查看")
        db.refresh(task); event(db,user,task.clue_id,task.id,data.action,before,target,note,data.result); audit(db,user,"INVESTIGATION_"+data.action,task.id)
        result=task_json(task); finish(record,result,200,task.id); db.commit(); return result
    return router
