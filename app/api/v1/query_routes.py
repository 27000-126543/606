from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from typing import Optional, List
from datetime import datetime, timezone
import os

from ...database import get_db
from ...models.user import User
from ...models.anomaly import Anomaly
from ...models.ticket import WorkOrder
from ...models.report import DailyReport
from ...models.audit import AuditLog
from ...utils.auth import get_current_user, require_role
from ...services.audit_service import audit_service
from ...services.query_service import query_service
from ...schemas.api import (
    ReportResponse,
    AuditListResponse, AuditQueryParams, AuditLogResponse,
    LogResponse, LogListResponse, LogQueryParams,
    ExportRequest, ExportResponse, SystemStatsResponse,
)
from ...utils.logger import logger


def _get_report_service():
    try:
        from ...services.report_service import report_service
        return report_service
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"报表服务暂不可用: {type(e).__name__}: {e}"
        )


def _get_task_scheduler():
    try:
        from ...services.task_scheduler import task_scheduler
        return task_scheduler
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"定时任务服务暂不可用: {type(e).__name__}: {e}"
        )

router = APIRouter(tags=["报表、日志与查询"])


@router.get("/reports/daily", dependencies=[Depends(require_role("supervisor"))])
async def list_daily_reports(
    page: int = 1,
    page_size: int = 30,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if start_date:
        conditions.append(DailyReport.report_date >= start_date)
    if end_date:
        conditions.append(DailyReport.report_date <= end_date)

    count_stmt = select(func.count(DailyReport.id))
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar() or 0)

    query = select(DailyReport)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(desc(DailyReport.report_date)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    reports = list(result.scalars().all())

    return {
        "code": 200,
        "message": "success",
        "data": [ReportResponse.model_validate(r, from_attributes=True).model_dump() for r in reports],
        "total": total,
    }


@router.post("/reports/daily/generate")
async def generate_daily_report(
    report_date: Optional[datetime] = None,
    current_user: User = Depends(require_role("supervisor")),
):
    report_service = _get_report_service()
    report = await report_service.generate_daily_report(report_date=report_date, save=True)
    return {
        "code": 200,
        "message": "报表生成成功",
        "data": {"report_id": str(report.id), "report_date": report.report_date.isoformat()},
    }


@router.get("/reports/{report_id}")
async def get_report_detail(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DailyReport).where(DailyReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="报表不存在")

    return {
        "code": 200,
        "message": "success",
        "data": report,
    }


@router.get("/reports/{report_id}/export/pdf")
async def export_report_pdf(
    report_id: str,
    current_user: User = Depends(get_current_user),
):
    report_service = _get_report_service()
    filepath = await report_service.export_report_pdf(report_id)
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="PDF文件生成失败")

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="report",
        action_type="export",
        action_desc=f"导出报表PDF: {report_id}",
        target_type="report",
        target_id=report_id,
        severity_level="info",
    )

    filename = os.path.basename(filepath)
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/pdf",
    )


@router.get("/reports/{report_id}/export/excel")
async def export_report_excel(
    report_id: str,
    current_user: User = Depends(get_current_user),
):
    report_service = _get_report_service()
    filepath = await report_service.export_report_excel(report_id)
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Excel文件生成失败")

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="report",
        action_type="export",
        action_desc=f"导出报表Excel: {report_id}",
        target_type="report",
        target_id=report_id,
        severity_level="info",
    )

    filename = os.path.basename(filepath)
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/audit-logs", response_model=AuditListResponse, dependencies=[Depends(require_role("supervisor"))])
async def list_audit_logs(
    user_id: Optional[str] = None,
    module: Optional[str] = None,
    action_type: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    system_name: Optional[str] = None,
    anomaly_id: Optional[str] = None,
    work_order_id: Optional[str] = None,
    severity_level: Optional[str] = None,
    status: Optional[str] = None,
    time_start: Optional[datetime] = None,
    time_end: Optional[datetime] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    logs, total = await audit_service.query_audit_logs(
        user_id=user_id,
        module=module,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        system_name=system_name,
        anomaly_id=anomaly_id,
        work_order_id=work_order_id,
        severity_level=severity_level,
        status=status,
        time_start=time_start,
        time_end=time_end,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return AuditListResponse(
        data=[AuditLogResponse.model_validate(l, from_attributes=True) for l in logs],
        total=total,
    )


@router.get("/logs", response_model=LogListResponse)
async def list_logs(
    system_name: Optional[str] = None,
    log_level: Optional[List[str]] = Query(None),
    module: Optional[str] = None,
    trace_id: Optional[str] = None,
    host_ip: Optional[str] = None,
    time_start: Optional[datetime] = None,
    time_end: Optional[datetime] = None,
    keyword: Optional[str] = None,
    sort_by: str = "log_time",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 100,
    current_user: User = Depends(get_current_user),
):
    logs, total, stats = await query_service.query_logs(
        system_name=system_name,
        log_level=log_level,
        module=module,
        trace_id=trace_id,
        host_ip=host_ip,
        time_start=time_start,
        time_end=time_end,
        keyword=keyword,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return LogListResponse(
        data=[LogResponse.model_validate(l, from_attributes=True) for l in logs],
        total=total,
        stats=stats,
    )


@router.post("/export")
async def batch_export_data(
    request: ExportRequest,
    current_user: User = Depends(get_current_user),
):
    filters = request.filters or {}

    if request.format == "csv":
        if request.data_type == "anomalies":
            filepath = await query_service.export_anomalies_csv(**filters)
        elif request.data_type == "work_orders":
            filepath = await query_service.export_work_orders_csv(**filters)
        elif request.data_type == "logs":
            filepath = await query_service.export_logs_csv(**filters)
        elif request.data_type == "audit":
            data = await audit_service.batch_export_audit_logs(**filters)
            filepath = await query_service.export_json("audit", data)
        else:
            raise HTTPException(status_code=400, detail="不支持的导出类型")
    elif request.format == "json":
        if request.data_type == "anomalies":
            items, _, _ = await query_service.query_anomalies(**filters, page=1, page_size=100000)
        elif request.data_type == "work_orders":
            items, _, _ = await query_service.query_work_orders(**filters, page=1, page_size=100000)
        elif request.data_type == "logs":
            items, _, _ = await query_service.query_logs(**filters, page=1, page_size=500000)
        else:
            data = await audit_service.batch_export_audit_logs(**filters)
            filepath = await query_service.export_json(request.data_type, data)
            items = None

        if items is not None:
            filepath = await query_service.export_json(request.data_type, items)
    else:
        raise HTTPException(status_code=400, detail="不支持的导出格式")

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="query",
        action_type="export",
        action_desc=f"批量导出 {request.data_type} ({request.format})",
        target_type=request.data_type,
        severity_level="info",
    )

    filename = os.path.basename(filepath)
    return ExportResponse(
        data={
            "file_path": filepath,
            "filename": filename,
            "download_url": f"/api/v1/query/download/{filename}",
        }
    )


@router.get("/download/{filename}")
async def download_exported_file(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    from ...config import settings
    filepath = os.path.join(settings.REPORT_EXPORT_DIR, filename)

    if not os.path.exists(filepath) or ".." in filename:
        raise HTTPException(status_code=404, detail="文件不存在")

    if filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif filename.endswith(".csv"):
        media_type = "text/csv"
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename.endswith(".json"):
        media_type = "application/json"
    elif filename.endswith(".png"):
        media_type = "image/png"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        path=filepath,
        filename=filename,
        media_type=media_type,
    )


@router.get("/system/stats", response_model=SystemStatsResponse)
async def get_system_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    from datetime import timedelta
    from ...models.user import UserTeam

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    team_ids = None
    user_id = None
    if current_user.role == "operator":
        team_ids_result = await db.execute(
            select(UserTeam.team_id).where(UserTeam.user_id == current_user.id)
        )
        team_ids = [str(r[0]) for r in team_ids_result.fetchall()]
        user_id = str(current_user.id)

    anomaly_permission_conditions = []
    ticket_permission_conditions = []
    if team_ids is not None or user_id is not None:
        wo_conditions = []
        if team_ids:
            wo_conditions.append(WorkOrder.assigned_team_id.in_(team_ids))
        if user_id:
            wo_conditions.append(WorkOrder.assignee_id == user_id)
        
        if wo_conditions:
            wo_subquery = select(WorkOrder.anomaly_id).where(or_(*wo_conditions))
            anomaly_permission_conditions.append(Anomaly.id.in_(wo_subquery))
            ticket_permission_conditions.append(or_(*wo_conditions))
        else:
            anomaly_permission_conditions.append(Anomaly.id.in_(select(WorkOrder.anomaly_id).where(or_(False, False))))
            ticket_permission_conditions.append(or_(False, False))

    anomaly_count = await db.execute(
        select(func.count(Anomaly.id)).where(
            and_(Anomaly.detected_time >= today_start, *anomaly_permission_conditions)
        )
    )

    ticket_count = await db.execute(
        select(func.count(WorkOrder.id)).where(
            and_(WorkOrder.created_at >= today_start, *ticket_permission_conditions)
        )
    )

    pending_count = await db.execute(
        select(func.count(WorkOrder.id)).where(
            and_(
                WorkOrder.status.in_(["pending", "assigned", "in_progress", "verifying"]),
                *ticket_permission_conditions
            )
        )
    )

    critical_open = await db.execute(
        select(func.count(Anomaly.id)).where(
            and_(
                Anomaly.severity == "critical",
                Anomaly.status.in_(["open", "investigating"]),
                *anomaly_permission_conditions
            )
        )
    )

    sla_breach_count = await db.execute(
        select(func.count(WorkOrder.id)).where(
            and_(
                WorkOrder.sla_deadline.isnot(None),
                or_(
                    and_(WorkOrder.status.in_(["pending", "assigned", "in_progress"]),
                         WorkOrder.sla_deadline < datetime.now(timezone.utc)),
                    and_(WorkOrder.resolved_at.isnot(None),
                         WorkOrder.resolved_at > WorkOrder.sla_deadline),
                ),
                *ticket_permission_conditions
            )
        )
    )

    trend_7days = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_count = await db.execute(
            select(func.count(Anomaly.id)).where(
                and_(
                    Anomaly.detected_time >= day_start,
                    Anomaly.detected_time < day_end,
                    *anomaly_permission_conditions
                )
            )
        )
        trend_7days.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "count": int(day_count.scalar() or 0),
        })

    data = {
        "today_anomalies": int(anomaly_count.scalar() or 0),
        "today_tickets": int(ticket_count.scalar() or 0),
        "pending_tickets": int(pending_count.scalar() or 0),
        "critical_open": int(critical_open.scalar() or 0),
        "sla_breach_count": int(sla_breach_count.scalar() or 0),
        "trend_7days": trend_7days,
    }

    return SystemStatsResponse(data=data)


@router.get("/system/health")
async def system_health_check():
    task_scheduler = _get_task_scheduler()
    health = await task_scheduler._system_health_check()
    return {"code": 200, "message": "success", "data": health}


@router.get("/system/scheduler-status", dependencies=[Depends(require_role("supervisor"))])
async def scheduler_status():
    task_scheduler = _get_task_scheduler()
    status = task_scheduler.get_job_status()
    return {"code": 200, "message": "success", "data": status}
