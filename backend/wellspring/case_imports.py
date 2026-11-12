"""虚构数据的案件 CSV 暂存与新增记录导入；不更新已有案件。"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .development_tools import parse_case_csv
from .models import Case, CaseImportBatch, CaseImportRow, User
from .security import current_user

class StageInput(BaseModel):
    source: str = Field(min_length=1,max_length=200)
    content: str = Field(max_length=100000)


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix="/api/imports/case-batches",tags=["案件导入（开发验证）"])
    def batch_for(db,user,batch_id):
        batch=db.scalar(select(CaseImportBatch).where(CaseImportBatch.id==batch_id,CaseImportBatch.org_id==user.org_id,CaseImportBatch.actor_id==user.id))
        if not batch:raise error(404,"NOT_FOUND","批次不存在或无权访问")
        return batch
    def batch_json(batch):
        return {"id":batch.id,"source":batch.source,"sha256":batch.digest,"mapping_version":batch.mapping_version,"status":batch.status,"created_at":batch.created_at,"completed_at":batch.completed_at}
    def row_json(row):
        return {"id":row.id,"row":row.line_number,"number":row.number,"title":row.title,"preview_status":row.preview_status,"result_status":row.result_status,"reason":row.reason,"case_id":row.case_id}
    @router.post("",status_code=201)
    def stage(data:StageInput,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        source=data.source.strip()
        if not source:raise error(422,"VALIDATION_ERROR","来源不能为空")
        digest,rows=parse_case_csv(data.content,error)
        if not rows:raise error(422,"EMPTY_IMPORT","文件没有数据行")
        record,replay=reserve(db,user,"CASE_IMPORT_STAGE",key,{"source":source,"digest":digest,"mapping_version":"DEV-1"})
        if replay:return replay
        numbers={r['number'] for r in rows if r['valid']}
        existing=set(db.scalars(select(Case.number).where(Case.org_id==user.org_id,Case.number.in_(numbers))).all()) if numbers else set()
        batch=CaseImportBatch(org_id=user.org_id,actor_id=user.id,source=source,digest=digest,mapping_version="DEV-1",status="PREVIEW")
        db.add(batch);db.flush()
        for item in rows:
            state='ERROR' if not item['valid'] else 'CONFLICT' if item['number'] in existing else 'NEW'
            reason='；'.join(item['errors']) if item['errors'] else ('本组织编号已存在，需人工核对' if state=='CONFLICT' else '')
            db.add(CaseImportRow(batch_id=batch.id,line_number=item['row'],number=item['number'],title=item['title'],preview_status=state,reason=reason))
        audit(db,user,"CASE_IMPORT_STAGE",batch.id);result=batch_json(batch);finish(record,result,201,batch.id);db.commit();return result
    @router.get("")
    def listing(request:Request,page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
        stmt=select(CaseImportBatch).where(CaseImportBatch.org_id==user.org_id,CaseImportBatch.actor_id==user.id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.scalars(stmt.order_by(CaseImportBatch.created_at.desc(),CaseImportBatch.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        audit(db,user,"CASE_IMPORT_LIST",user.id);db.commit();return page_result([batch_json(row) for row in rows],page,page_size,total,request_id(request))
    @router.get("/{batch_id}")
    def detail(batch_id:str,request:Request,page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
        batch=batch_for(db,user,batch_id);stmt=select(CaseImportRow).where(CaseImportRow.batch_id==batch.id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.scalars(stmt.order_by(CaseImportRow.line_number).offset((page-1)*page_size).limit(page_size)).all()
        audit(db,user,"CASE_IMPORT_VIEW",batch.id);db.commit();return {"batch":batch_json(batch),"rows":page_result([row_json(row) for row in rows],page,page_size,total,request_id(request))}
    @router.post("/{batch_id}/cancel")
    def cancel(batch_id:str,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        batch=batch_for(db,user,batch_id)
        record,replay=reserve(db,user,"CASE_IMPORT_CANCEL",key,{"batch_id":batch_id,"digest":batch.digest})
        if replay:return replay
        claimed=db.execute(update(CaseImportBatch).where(CaseImportBatch.id==batch_id,CaseImportBatch.org_id==user.org_id,CaseImportBatch.actor_id==user.id,CaseImportBatch.status=="PREVIEW").values(status="CANCELLED",completed_at=datetime.now(timezone.utc)))
        if claimed.rowcount!=1:raise error(409,"BATCH_STATE_CONFLICT","批次已处理或不能取消，请查看结果")
        audit(db,user,"CASE_IMPORT_CANCEL",batch_id)
        result={"batch_id":batch_id,"status":"CANCELLED"};finish(record,result,200,batch_id);db.commit();return result
    @router.post("/{batch_id}/confirm")
    def confirm(batch_id:str,key:str | None=Header(None,alias="Idempotency-Key"),user:User=Depends(current_user),db:Session=Depends(get_db)):
        batch=batch_for(db,user,batch_id)
        record,replay=reserve(db,user,"CASE_IMPORT_CONFIRM",key,{"batch_id":batch_id,"digest":batch.digest,"mapping_version":batch.mapping_version})
        if replay:return replay
        claimed=db.execute(update(CaseImportBatch).where(CaseImportBatch.id==batch_id,CaseImportBatch.org_id==user.org_id,CaseImportBatch.actor_id==user.id,CaseImportBatch.status=="PREVIEW").values(status="PROCESSING"))
        if claimed.rowcount!=1:raise error(409,"BATCH_STATE_CONFLICT","批次已处理或正在处理，请查看结果")
        rows=db.scalars(select(CaseImportRow).where(CaseImportRow.batch_id==batch.id).order_by(CaseImportRow.line_number)).all()
        counts={"created":0,"conflict":0,"error":0}
        for row in rows:
            if row.preview_status!='NEW':
                row.result_status=row.preview_status;counts['error' if row.preview_status=='ERROR' else 'conflict']+=1;continue
            savepoint=db.begin_nested()
            try:
                case=Case(org_id=user.org_id,number=row.number,title=row.title,status='DRAFT')
                db.add(case);db.flush()
            except IntegrityError:
                savepoint.rollback()
                existing=db.scalar(select(Case.id).where(Case.org_id==user.org_id,Case.number==row.number))
                if not existing:raise
                row.result_status='CONFLICT';row.reason='确认时编号已存在，未覆盖';counts['conflict']+=1
                continue
            # 审计或其他写入失败不得被当作编号冲突；外层事务必须全部回滚。
            audit(db,user,"CASE_IMPORT_CREATE",case.id)
            row.case_id=case.id;row.result_status='CREATED';row.reason=''
            db.flush();savepoint.commit();counts['created']+=1
        batch.status='COMPLETED' if counts['created']==len(rows) else 'PARTIAL' if counts['created'] else 'NO_CHANGE'
        batch.completed_at=datetime.now(timezone.utc)
        audit(db,user,"CASE_IMPORT_CONFIRM",batch.id)
        result={"batch_id":batch.id,"status":batch.status,"counts":counts,"total":len(rows)}
        finish(record,result,200,batch.id);db.commit();return result
    return router
