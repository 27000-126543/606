from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import Optional, List
from datetime import datetime, timezone

from ...database import get_db
from ...models.user import User, UserTeam
from ...models.anomaly import Anomaly
from ...models.ticket import WorkOrder
from ...utils.auth import get_current_user, require_role
from ...services.audit_service import audit_service
from ...services.root_cause_analyzer import root_cause_analyzer
from ...services.ticket_service import ticket_service
from ...schemas.api import (
    AnomalyResponse, AnomalyListResponse, AnomalyQueryParams,
    WorkOrderResponse, WorkOrderListResponse, WorkOrderQueryParams,
    WorkOrderStatusUpdate, WorkOrderReassign,
    RootCauseAnalysisResponse, CaseMatchRequest, CaseMatchResponse,
    CaseImportRequest,
)
from ...utils.logger import logger


def _get_case_matcher():
    try:
        from ...services.case_matcher import case_matcher
        return case_matcher
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"案例匹配服务暂不可用: {type(e).__name__}: {e}"
        )


def _get_query_service():
    try:
        from ...services.query_service import query_service
        return query_service
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"查询服务暂不可用: {type(e).__name__}: {e}"
        )

router = APIRouter(tags=["异常管理"])


def _get_user_team_ids(user: User) -> List[str]:
    return []


@router.get("", response_model=AnomalyListResponse)
async def list_anomalies(
    system_name: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    severity: Optional[List[str]] = Query(None),
    status: Optional[List[str]] = Query(None),
    impact_scope: Optional[str] = None,
    time_start: Optional[datetime] = None,
    time_end: Optional[datetime] = None,
    keyword: Optional[str] = None,
    sort_by: str = "detected_time",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    team_ids = None
    user_id = None
    if current_user.role == "operator":
        team_ids_result = await db.execute(
            select(UserTeam.team_id).where(UserTeam.user_id == current_user.id)
        )
        team_ids = [str(r[0]) for r in team_ids_result.fetchall()]
        user_id = str(current_user.id)

    query_service = _get_query_service()
    anomalies, total, stats = await query_service.query_anomalies(
        system_name=system_name,
        anomaly_type=anomaly_type,
        severity=severity,
        status=status,
        impact_scope=impact_scope,
        time_start=time_start,
        time_end=time_end,
        keyword=keyword,
        team_ids=team_ids,
        user_id=user_id,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )

    return AnomalyListResponse(
        data=[AnomalyResponse.model_validate(a, from_attributes=True) for a in anomalies],
        total=total,
        stats=stats,
    )


@router.get("/{anomaly_id}", response_model=AnomalyResponse)
async def get_anomaly_detail(
    anomaly_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Anomaly).where(Anomaly.id == anomaly_id))
    anomaly = result.scalar_one_or_none()

    if not anomaly:
        raise HTTPException(status_code=404, detail="异常记录不存在")

    if current_user.role == "operator":
        team_ids_result = await db.execute(
            select(UserTeam.team_id).where(UserTeam.user_id == current_user.id)
        )
        team_ids = [str(r[0]) for r in team_ids_result.fetchall()]
        user_id = str(current_user.id)

        wo_conditions = []
        if team_ids:
            wo_conditions.append(WorkOrder.assigned_team_id.in_(team_ids))
        wo_conditions.append(WorkOrder.assignee_id == user_id)
        
        wo_result = await db.execute(
            select(WorkOrder).where(
                and_(
                    WorkOrder.anomaly_id == anomaly.id,
                    or_(*wo_conditions),
                )
            )
        )
        if not wo_result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="无权限查看此异常")

    return AnomalyResponse.model_validate(anomaly, from_attributes=True)


@router.post("/{anomaly_id}/analyze", response_model=RootCauseAnalysisResponse)
async def analyze_root_cause(
    anomaly_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Anomaly).where(Anomaly.id == anomaly_id))
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404, detail="异常记录不存在")

    if current_user.role == "operator":
        team_ids_result = await db.execute(
            select(UserTeam.team_id).where(UserTeam.user_id == current_user.id)
        )
        team_ids = [str(r[0]) for r in team_ids_result.fetchall()]
        user_id = str(current_user.id)

        wo_conditions = []
        if team_ids:
            wo_conditions.append(WorkOrder.assigned_team_id.in_(team_ids))
        wo_conditions.append(WorkOrder.assignee_id == user_id)
        
        wo_result = await db.execute(
            select(WorkOrder).where(
                and_(
                    WorkOrder.anomaly_id == anomaly.id,
                    or_(*wo_conditions),
                )
            )
        )
        if not wo_result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="无权限查看此异常")

    analysis = await root_cause_analyzer.analyze_anomaly(anomaly_id, db)

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="anomaly",
        action_type="analyze",
        action_desc=f"执行根因分析: anomaly_id={anomaly_id}",
        target_type="anomaly",
        target_id=anomaly_id,
        system_name=anomaly.system_name,
        anomaly_id=anomaly_id,
        severity_level="info",
        db=db,
    )

    return RootCauseAnalysisResponse(data=analysis)


@router.post("/{anomaly_id}/create-work-order", response_model=WorkOrderResponse)
async def create_work_order(
    anomaly_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Anomaly).where(Anomaly.id == anomaly_id))
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404, detail="异常记录不存在")

    if current_user.role == "operator":
        team_ids_result = await db.execute(
            select(UserTeam.team_id).where(UserTeam.user_id == current_user.id)
        )
        team_ids = [str(r[0]) for r in team_ids_result.fetchall()]
        user_id = str(current_user.id)

        wo_conditions = []
        if team_ids:
            wo_conditions.append(WorkOrder.assigned_team_id.in_(team_ids))
        wo_conditions.append(WorkOrder.assignee_id == user_id)
        
        wo_result = await db.execute(
            select(WorkOrder).where(
                and_(
                    WorkOrder.anomaly_id == anomaly.id,
                    or_(*wo_conditions),
                )
            )
        )
        if not wo_result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="无权限操作此异常")

    wo_result = await db.execute(
        select(WorkOrder).where(WorkOrder.anomaly_id == anomaly.id)
    )
    if wo_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该异常已关联工单")

    work_order = await ticket_service.create_work_order_for_anomaly(anomaly_id, db)
    if not work_order:
        raise HTTPException(status_code=500, detail="创建工单失败")

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="ticket",
        action_type="create",
        action_desc=f"为异常创建工单: {work_order.order_no}",
        target_type="work_order",
        target_id=str(work_order.id),
        target_name=work_order.title,
        anomaly_id=anomaly_id,
        system_name=anomaly.system_name,
        db=db,
    )

    return WorkOrderResponse.model_validate(work_order, from_attributes=True)


@router.post("/{anomaly_id}/match-cases", response_model=CaseMatchResponse)
async def match_similar_cases(
    anomaly_id: str,
    top_k: int = 5,
    min_score: float = 0.5,
    current_user: User = Depends(get_current_user),
):
    case_matcher = _get_case_matcher()
    matches = await case_matcher.find_similar_cases(
        anomaly_id=anomaly_id,
        top_k=top_k,
        min_score=min_score,
    )
    return CaseMatchResponse(data=matches)


@router.post("/import-case")
async def import_case_to_library(
    request: CaseImportRequest,
    current_user: User = Depends(get_current_user),
):
    case_matcher = _get_case_matcher()
    case = await case_matcher.import_event_to_case_library(
        event_data=request.model_dump(),
        created_by=str(current_user.id),
    )
    if not case:
        raise HTTPException(status_code=500, detail="导入案例失败")

    return {
        "code": 200,
        "message": "案例导入成功",
        "data": {"case_id": str(case.id), "case_no": case.case_no},
    }


@router.post("/case-match")
async def manual_case_match(
    request: CaseMatchRequest,
    current_user: User = Depends(get_current_user),
):
    case_matcher = _get_case_matcher()
    matches = await case_matcher.find_similar_cases(
        anomaly_id=request.anomaly_id,
        event_data=request.event_data,
        top_k=request.top_k,
        min_score=request.min_score,
    )
    return CaseMatchResponse(data=matches)
