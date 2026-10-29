"""证物盘点观测：保留实测差异，不直接改变余额。"""
from datetime import timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from .db import get_db
from .models import Evidence, EvidenceInventoryObservation, User
from .security import current_user

class ObservationCreate(BaseModel):
    evidence_version: int = Field(ge=1)
    observed_weight: Decimal = Field(ge=0, max_digits=20, decimal_places=6)
    note: str = Field(min_length=1, max_length=1000)


def create_router(error, audit, reserve, finish, page_result, request_id):
    router = APIRouter(prefix="/api/evidence", tags=["证物盘点（开发验证）"])

    def visible(db, user, evidence_id):
        item = db.scalar(select(Evidence).where(Evidence.id==evidence_id, Evidence.org_id==user.org_id))
        if not item: raise error(404,"NOT_FOUND","记录不存在或无权访问")
        return item

    def as_json(row):
        recorded_at = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        return {"id":row.id,"evidence_id":row.evidence_id,"book_weight":str(row.book_weight),
                "observed_weight":str(row.observed_weight),"difference":str(row.difference),
                "evidence_version":row.evidence_version,"note":row.note,"actor_id":row.actor_id,"created_at":recorded_at.isoformat()}

    @router.get("/{evidence_id}/inventory-observations")
    def list_observations(evidence_id: str, request: Request, page: int = Query(1, ge=1, le=100000),
                          page_size: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        visible(db,user,evidence_id)
        stmt=select(EvidenceInventoryObservation).where(EvidenceInventoryObservation.evidence_id==evidence_id, EvidenceInventoryObservation.org_id==user.org_id)
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows=db.scalars(stmt.order_by(EvidenceInventoryObservation.created_at.desc(),EvidenceInventoryObservation.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        audit(db,user,"EVIDENCE_INVENTORY_VIEW",evidence_id);db.commit()
        return page_result([as_json(row) for row in rows],page,page_size,total,request_id(request))

    @router.post("/{evidence_id}/inventory-observations", status_code=201)
    def create_observation(evidence_id: str, data: ObservationCreate, key: str | None = Header(None,alias="Idempotency-Key"),
                           user: User = Depends(current_user), db: Session = Depends(get_db)):
        item=visible(db,user,evidence_id)
        note=data.note.strip()
        if not note: raise error(422,"VALIDATION_ERROR","盘点说明不能为空")
        body={"evidence_id":evidence_id,"evidence_version":data.evidence_version,"observed_weight":str(data.observed_weight),"note":note}
        record,replay=reserve(db,user,"EVIDENCE_INVENTORY_CREATE",key,body)
        if replay: return replay
        # 通过条件更新锁定当前证物版本，盘点只推进版本，不变更账面余额。
        changed=db.execute(update(Evidence).where(Evidence.id==evidence_id,Evidence.org_id==user.org_id,Evidence.version==data.evidence_version).values(version=Evidence.version+1))
        if changed.rowcount != 1: raise error(409,"VERSION_CONFLICT","证物已变化，请重新核对账面量后再盘点")
        db.refresh(item)
        row=EvidenceInventoryObservation(org_id=user.org_id,evidence_id=item.id,book_weight=item.balance,
              observed_weight=data.observed_weight,difference=data.observed_weight-item.balance,
              evidence_version=data.evidence_version,note=note,actor_id=user.id)
        db.add(row);db.flush();audit(db,user,"EVIDENCE_INVENTORY_CREATE",row.id)
        result=as_json(row);finish(record,result,201,row.id);db.commit();return result
    return router
