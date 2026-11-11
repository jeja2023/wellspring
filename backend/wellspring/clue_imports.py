"""Excel row preview and transactional, non-overwriting clue intake."""
from datetime import date
import hashlib
import json
from typing import Literal
from fastapi import APIRouter,Depends,Header,Request,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from sqlalchemy import func,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Clue,ClueImportBatch,IntelligenceEvent,User
from .security import current_user
from .clue_deliveries import lock_flow


class ImportRow(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    row_number:int=Field(ge=2,le=201)
    reference_no:str=Field(min_length=1,max_length=80)
    title:str=Field(min_length=1,max_length=200)
    source:str=Field(min_length=1,max_length=200)
    summary:str=Field(min_length=1,max_length=10000)
    priority:Literal['NORMAL','IMPORTANT']='NORMAL'
    due_date:date|None=None


class ImportInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    filename:str=Field(default='线索导入.xlsx',min_length=1,max_length=200)
    rows:list[dict]=Field(min_length=1,max_length=200)


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix='/api/intelligence/imports',tags=['线索Excel导入'])

    def validate(data,user,db):
        if sum(len(json.dumps(row,ensure_ascii=False)) for row in data.rows)>2_000_000:
            raise error(413,'IMPORT_TOO_LARGE','导入内容不能超过 200 万字符')
        numbers=[row['reference_no'].strip() for row in data.rows if isinstance(row.get('reference_no'),str)]
        existing=set(db.scalars(select(Clue.reference_no).where(Clue.org_id==user.org_id,Clue.reference_no.in_(numbers)))) if numbers else set()
        seen=set();output=[]
        for index,raw in enumerate(data.rows):
            issues=[];value=None
            try:value=ImportRow.model_validate(raw)
            except ValidationError as exc:
                labels={'reference_no':'线索编号','title':'标题','source':'来源','summary':'线索内容','priority':'重要程度','due_date':'办理期限','row_number':'行号'}
                issues=[labels.get(str(item['loc'][0]),'字段')+'格式或长度无效' for item in exc.errors()]
            if value:
                if value.reference_no in existing:issues.append('本组织线索编号已存在')
                if value.reference_no in seen:issues.append('文件内线索编号重复')
                seen.add(value.reference_no)
            output.append({'row_number':raw.get('row_number',index+2),'title':str(raw.get('title',''))[:200],'reference_no':str(raw.get('reference_no',''))[:80],
                'valid':not issues,'errors':issues,'value':value})
        return output

    @router.post('/preview')
    def preview(data:ImportInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
        rows=validate(data,user,db);audit(db,user,'CLUE_IMPORT_PREVIEW',user.org_id);db.commit()
        return {'rows':[{key:value for key,value in row.items() if key!='value'} for row in rows], 'valid_count':sum(row['valid'] for row in rows),'invalid_count':sum(not row['valid'] for row in rows)}

    @router.post('/confirm',status_code=201)
    def confirm(data:ImportInput,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
        lock_flow(db,user,'intelligence.import',error)
        record,replay=reserve(db,user,'CLUE_EXCEL_IMPORT',key,data.model_dump())
        if replay:return replay
        rows=validate(data,user,db)
        bad=[row for row in rows if not row['valid']]
        if bad:raise error(422,'IMPORT_INVALID','请修正预览中的错误后重新导入',[{'field':f"Excel 第 {row['row_number']} 行",'message':'；'.join(row['errors'])} for row in bad[:20]])
        batch=ClueImportBatch(org_id=user.org_id,actor_id=user.id,filename=data.filename,content_sha256=hashlib.sha256(json.dumps(data.rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),total=len(rows))
        db.add(batch);db.flush()
        for row in rows:
            value=row['value']
            clue=Clue(org_id=user.org_id,created_by=user.id,title=value.title,summary=value.summary,source=value.source,
                reference_no=value.reference_no,priority=value.priority,suggested_due_date=value.due_date,import_batch_id=batch.id)
            db.add(clue)
            try:db.flush()
            except IntegrityError:
                db.rollback();raise error(409,'IMPORT_DUPLICATE','编号在导入期间已被其他操作使用，请重新预览') from None
            db.add(IntelligenceEvent(org_id=user.org_id,clue_id=clue.id,actor_id=user.id,action='IMPORTED',after_status='DRAFT',note=f'Excel 第 {value.row_number} 行导入，待核验'))
        result={'id':batch.id,'imported':len(rows),'filename':batch.filename}
        audit(db,user,'CLUE_IMPORT_CONFIRM',batch.id);finish(record,result,201,batch.id);db.commit();return result

    @router.get('/batches')
    def batches(request:Request,page:int=Query(1,ge=1,le=100000),user:User=Depends(current_user),db:Session=Depends(get_db)):
        where=ClueImportBatch.org_id==user.org_id
        total=db.scalar(select(func.count()).select_from(ClueImportBatch).where(where)) or 0
        rows=db.scalars(select(ClueImportBatch).where(where).order_by(ClueImportBatch.created_at.desc(),ClueImportBatch.id.desc()).offset((page-1)*20).limit(20)).all()
        result=[{key:getattr(row,key) for key in ['id','filename','total','created_at']} for row in rows]
        audit(db,user,'CLUE_IMPORT_HISTORY',user.org_id);db.commit();return page_result(result,page,20,total,request_id(request))

    return router
