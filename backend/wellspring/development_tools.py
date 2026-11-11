"""开发环境的数据导入预览、个人审计和 AI 服务状态。"""
import csv
import hashlib
import io
from datetime import timezone
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .db import get_db
from .models import Audit, User
from .security import current_user

MAX_BYTES=100_000
MAX_ROWS=1000
EXPECTED_HEADERS=["案件编号","案件名称"]

class ImportPreview(BaseModel):
    content: str = Field(max_length=100_000)


def parse_case_csv(content, error):
    data=ImportPreview(content=content)
    raw=data.content.encode("utf-8")
    if len(raw)>MAX_BYTES: raise error(413,"IMPORT_TOO_LARGE","文件内容不能超过 100 KB")
    if "\x00" in data.content: raise error(422,"INVALID_FILE","文件内容包含无效字符")
    digest=hashlib.sha256(raw).hexdigest()
    try:
        reader=csv.reader(io.StringIO(data.content.lstrip("\ufeff"),newline=""),strict=True)
        header=next(reader,None)
        if header!=EXPECTED_HEADERS: raise error(422,"INVALID_TEMPLATE","表头必须依次为：案件编号,案件名称")
        rows=[];seen=set()
        while True:
            number=reader.line_num+1
            row=next(reader,None)
            if row is None: break
            if len(rows)>=MAX_ROWS: raise error(413,"IMPORT_TOO_MANY_ROWS","最多预览 1000 行")
            errors=[]
            if len(row)!=2: errors.append("列数必须为 2")
            values=(row+["",""])[:2]
            case_number,title=(value.strip() for value in values)
            if not case_number or len(case_number)>80: errors.append("案件编号不能为空且不能超过 80 字符")
            if not title or len(title)>200: errors.append("案件名称不能为空且不能超过 200 字符")
            if any(value.startswith(("=","+","-","@")) for value in (case_number,title)):
                errors.append("内容不能以公式字符开头")
            if case_number and case_number in seen: errors.append("文件内案件编号重复")
            if case_number:seen.add(case_number)
            rows.append({"row":number,"number":case_number[:80],"title":title[:200],"errors":errors,"valid":not errors})
    except (csv.Error,UnicodeError):
        raise error(422,"INVALID_FILE","CSV 格式无效，请检查引号和编码")
    return digest, rows


def create_router(error,audit,page_result,request_id):
    router=APIRouter(prefix="/api",tags=["开发辅助（仅虚构数据）"])

    @router.post("/imports/case-csv-preview")
    def preview(data:ImportPreview,user:User=Depends(current_user),db:Session=Depends(get_db)):
        digest,rows=parse_case_csv(data.content,error)
        audit(db,user,"IMPORT_CASE_PREVIEW",user.org_id);db.commit()
        return {"sha256":digest,"rows":rows,"total":len(rows),"valid_count":sum(r["valid"] for r in rows),"invalid_count":sum(not r["valid"] for r in rows),"mode":"PREVIEW_ONLY"}

    @router.get("/audit/mine")
    def my_audit(request:Request,page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
        stmt=select(Audit).where(Audit.actor_id==user.id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.scalars(stmt.order_by(Audit.created_at.desc(),Audit.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        items=[]
        for row in rows:
            when=row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
            items.append({"id":row.id,"action":row.action,"object_id":row.object_id,"created_at":when.isoformat()})
        audit(db,user,"AUDIT_SELF_VIEW",user.id);db.commit()
        return page_result(items,page,page_size,total,request_id(request))

    return router
