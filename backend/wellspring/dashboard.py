"""Aggregate only authorized modules in the current organization; no record text."""
from datetime import datetime, time, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .access_policy import effective_permissions
from .db import get_db
from .models import Case, CaseInformation, Clue, InvestigationTask, Organization, PersonDraft, User
from .security import current_user
from .analysis_models import AnalysisAsset
from .wastewater_models import WastewaterResult, WastewaterSample, WastewaterSite

BEIJING = timezone(timedelta(hours=8))


def overview(db: Session, user: User, days: int, instant: datetime | None = None):
    instant = instant or datetime.now(timezone.utc)
    local_today = instant.astimezone(BEIJING).date()
    first_day = local_today - timedelta(days=days - 1)
    start = datetime.combine(first_day, time.min, BEIJING).astimezone(timezone.utc)
    dates = [(first_day + timedelta(days=index)).isoformat() for index in range(days)]
    permissions = effective_permissions(db, user)
    metrics, series, breakdowns = [], [], {}
    specifications = [
        ("intake", "接警信息", "条", CaseInformation, [CaseInformation.deleted_at.is_(None)]),
        ("cases", "案件记录", "件", Case, []),
        ("models", "业务模型", "个", AnalysisAsset, [AnalysisAsset.kind=="MODEL"]),
        ("intelligence", "情报线索", "条", Clue, []),
        ("persons", "人员档案", "份", PersonDraft, []),
        ("wastewater", "采样记录", "份", WastewaterSample, []),
    ]
    for key, label, unit, model, extra in specifications:
        if key + ".read" not in permissions:
            continue
        filters = [model.org_id == user.org_id, *extra]
        total = int(db.scalar(select(func.count()).select_from(model).where(*filters)) or 0)
        if db.get_bind().dialect.name == "postgresql":
            day = func.date(func.timezone("Asia/Shanghai", model.created_at))
        else:
            day = func.date(model.created_at, "+8 hours")
        daily = {str(date)[:10]: int(count) for date, count in db.execute(
            select(day, func.count()).where(*filters, model.created_at >= start, model.created_at <= instant).group_by(day)
        )}
        values = [daily.get(date, 0) for date in dates]
        metrics.append({"key": key, "label": label, "unit": unit, "total": total, "period_count": sum(values)})
        series.append({"key": key, "label": label, "values": values})

    def states(model, column, labels):
        counts = dict(db.execute(select(column, func.count()).where(model.org_id == user.org_id).group_by(column)).all())
        return [{"key": code, "label": label, "value": int(counts.pop(code, 0))} for code, label in labels] + (
            [{"key": "OTHER", "label": "其他状态", "value": int(sum(counts.values()))}] if counts else [])

    if "intake.read" in permissions:
        groups = db.execute(select(CaseInformation.alarm_type, func.count()).where(
            CaseInformation.org_id == user.org_id, CaseInformation.deleted_at.is_(None)
        ).group_by(CaseInformation.alarm_type).order_by(func.count().desc(), CaseInformation.alarm_type).limit(6)).all()
        rows = [{"key": str(index), "label": (name or "未填写")[:80], "value": int(count)} for index, (name, count) in enumerate(groups)]
        total = next(item["total"] for item in metrics if item["key"] == "intake")
        remainder = total - sum(row["value"] for row in rows)
        if remainder:
            rows.append({"key": "other", "label": "其他类型", "value": remainder})
        breakdowns["intake"] = rows
    if "intelligence.read" in permissions:
        breakdowns["tasks"] = states(InvestigationTask, InvestigationTask.status,
            [("OPEN", "待办理"), ("PENDING_REVIEW", "待复核"), ("RETURNED", "已退回"), ("CLOSED", "已关闭")])
    if "models.read" in permissions:
        counts=dict(db.execute(select(AnalysisAsset.status,func.count()).where(AnalysisAsset.org_id==user.org_id,AnalysisAsset.kind=='MODEL').group_by(AnalysisAsset.status)).all())
        breakdowns['models']=[{'key':key,'label':label,'value':int(counts.get(key,0))} for key,label in [('DRAFT','未启用'),('ACTIVE','已启用'),('ARCHIVED','已归档')]]
    if "wastewater.read" in permissions:
        breakdowns["results"] = states(WastewaterResult, WastewaterResult.state,
            [("DRAFT", "待复核"), ("RETURNED", "已退回"), ("REVIEWED", "已复核")])
        breakdowns["sites"] = [
            {"key": "active", "label": "启用点位", "value": int(db.scalar(select(func.count()).select_from(WastewaterSite).where(WastewaterSite.org_id == user.org_id, WastewaterSite.active.is_(True))) or 0)},
            {"key": "inactive", "label": "停用点位", "value": int(db.scalar(select(func.count()).select_from(WastewaterSite).where(WastewaterSite.org_id == user.org_id, WastewaterSite.active.is_(False))) or 0)},
        ]
    organization = db.get(Organization, user.org_id)
    return {"generated_at": instant, "timezone": "Asia/Shanghai", "organization": organization.name if organization else "",
        "range": {"days": days, "start_date": first_day.isoformat(), "end_date": local_today.isoformat()},
        "metrics": metrics, "trend": {"dates": dates, "series": series}, "breakdowns": breakdowns,
        "date_basis": "新增趋势按记录创建时间及北京时间统计；总量和状态分布为当前组织全量，隐藏接警不计入。"}


def create_router(audit):
    router = APIRouter(prefix="/api/dashboard", tags=["数据大屏"])

    @router.get("/overview")
    def dashboard(days: int = Query(30), user: User = Depends(current_user), db: Session = Depends(get_db)):
        if days not in {7,30,90}:
            raise HTTPException(status_code=422, detail={"code":"VALIDATION_ERROR","message":"统计周期只支持 7、30 或 90 天","details":[]})
        result = overview(db, user, days)
        audit(db, user, "DASHBOARD_VIEW", user.org_id)
        db.commit()
        return result

    return router
