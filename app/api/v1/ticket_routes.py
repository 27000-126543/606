from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, List
from datetime import datetime, timezone

from ...database import get_db
from ...models.user import User, UserTeam
from ...models.ticket import WorkOrder, FollowUpTask
from ...utils.auth import get_current_user, require_role
from ...services.ticket_service import ticket_service
from ...services.playbook_executor import playbook_executor
from ...services.audit_service import audit_service
from ...schemas.api import (
    WorkOrderResponse, WorkOrderListResponse, WorkOrderQueryParams,
    WorkOrderStatusUpdate, WorkOrderReassign,
    PlaybookResponse, PlaybookExecuteRequest, PlaybookExecutionResponse,
    PlaybookApprovalRequest,
)
from ...utils.logger import logger

router = APIRouter(tags=["工单与预案"])


@router.get("/work-orders", response_model=WorkOrderListResponse)
async def list_work_orders(
    assigned_team_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    anomaly_id: Optional[str] = None,
    priority: Optional[List[str]] = Query(None),
    severity: Optional[List[str]] = Query(None),
    status: Optional[List[str]] = Query(None),
    is_escalated: Optional[bool] = None,
    sla_breach: Optional[bool] = None,
    time_start: Optional[datetime] = None,
    time_end: Optional[datetime] = None,
    keyword: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_teams = None
    user_id = None
    if current_user.role == "operator":
        team_ids_result = await db.execute(
            select(UserTeam.team_id).where(UserTeam.user_id == current_user.id)
        )
        user_teams = [str(r[0]) for r in team_ids_result.fetchall()]
        user_id = str(current_user.id)

    from ...services.query_service import query_service
    orders, total, stats = await query_service.query_work_orders(
        assigned_team_id=assigned_team_id,
        assignee_id=assignee_id,
        user_teams=user_teams,
        user_id=user_id,
        anomaly_id=anomaly_id,
        priority=priority,
        severity=severity,
        status=status,
        is_escalated=is_escalated,
        sla_breach=sla_breach,
        time_start=time_start,
        time_end=time_end,
        keyword=keyword,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )

    return WorkOrderListResponse(
        data=[WorkOrderResponse.model_validate(o, from_attributes=True) for o in orders],
        total=total,
        stats=stats,
    )


@router.get("/work-orders/{order_id}", response_model=WorkOrderResponse)
async def get_work_order_detail(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkOrder).where(WorkOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    if current_user.role == "operator":
        team_ids_result = await db.execute(
            select(UserTeam.team_id).where(UserTeam.user_id == current_user.id)
        )
        team_ids = [str(r[0]) for r in team_ids_result.fetchall()]
        if str(order.assigned_team_id) not in team_ids and str(order.assignee_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="无权限查看此工单")

    return WorkOrderResponse.model_validate(order, from_attributes=True)


@router.put("/work-orders/{order_id}/status", response_model=WorkOrderResponse)
async def update_work_order_status(
    order_id: str,
    request: WorkOrderStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_result = await db.execute(
        select(WorkOrder).where(WorkOrder.id == order_id)
    )
    order = check_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    if current_user.role == "operator":
        team_ids_result = await db.execute(
            select(UserTeam.team_id).where(UserTeam.user_id == current_user.id)
        )
        team_ids = [str(r[0]) for r in team_ids_result.fetchall()]
        if str(order.assigned_team_id) not in team_ids and str(order.assignee_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="无权限操作此工单")

    updated = await ticket_service.update_work_order_status(
        work_order_id=order_id,
        new_status=request.status,
        user_id=str(current_user.id),
        note=request.note,
        db=db,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="状态更新失败")

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="ticket",
        action_type="update",
        action_desc=f"更新工单状态: {order.order_no} -> {request.status}",
        target_type="work_order",
        target_id=order_id,
        target_name=order.title,
        status="success",
        work_order_id=order_id,
        db=db,
    )

    return WorkOrderResponse.model_validate(updated, from_attributes=True)


@router.put("/work-orders/{order_id}/reassign", response_model=WorkOrderResponse)
async def reassign_work_order(
    order_id: str,
    request: WorkOrderReassign,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_result = await db.execute(
        select(WorkOrder).where(WorkOrder.id == order_id)
    )
    order = check_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    if current_user.role != "supervisor":
        team_ids_result = await db.execute(
            select(UserTeam.team_id).where(
                and_(UserTeam.user_id == current_user.id, UserTeam.is_team_leader == True)
            )
        )
        lead_teams = [str(r[0]) for r in team_ids_result.fetchall()]
        if str(order.assigned_team_id) not in lead_teams:
            raise HTTPException(status_code=403, detail="无权限转派此工单")

    updated = await ticket_service.reassign_work_order(
        work_order_id=order_id,
        team_id=request.team_id,
        assignee_id=request.assignee_id,
        user_id=str(current_user.id),
        reason=request.reason,
        db=db,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="转派失败")

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="ticket",
        action_type="reassign",
        action_desc=f"转派工单: {order.order_no}",
        target_type="work_order",
        target_id=order_id,
        work_order_id=order_id,
        db=db,
    )

    return WorkOrderResponse.model_validate(updated, from_attributes=True)


@router.post("/playbooks/execute")
async def execute_playbook(
    request: PlaybookExecuteRequest,
    current_user: User = Depends(get_current_user),
):
    from ...models.playbook import Playbook
    import asyncio

    execution = await playbook_executor.execute_playbook(
        playbook_id=request.playbook_id,
        work_order_id=request.work_order_id,
        anomaly_id=request.anomaly_id,
        trigger_type="manual",
        executor_id=str(current_user.id),
        parameters=request.parameters,
    )

    if not execution:
        raise HTTPException(status_code=500, detail="预案执行失败")

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="playbook",
        action_type="execute",
        action_desc=f"执行预案: {execution.execution_no}",
        target_type="playbook_execution",
        target_id=str(execution.id),
        target_name=execution.execution_no,
        work_order_id=request.work_order_id,
        anomaly_id=request.anomaly_id,
        severity_level="warning",
    )

    return {
        "code": 200,
        "message": "预案执行已启动",
        "data": {"execution_id": str(execution.id), "execution_no": execution.execution_no, "status": execution.status},
    }


@router.get("/playbook-executions/{execution_id}")
async def get_playbook_execution(
    execution_id: str,
    current_user: User = Depends(get_current_user),
):
    execution = await playbook_executor.get_execution_status(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")

    return {
        "code": 200,
        "message": "success",
        "data": PlaybookExecutionResponse.model_validate(execution, from_attributes=True).model_dump(),
    }


@router.put("/playbook-executions/{execution_id}/approve")
async def approve_playbook_execution(
    execution_id: str,
    request: PlaybookApprovalRequest,
    current_user: User = Depends(require_role("supervisor")),
):
    execution = await playbook_executor.approve_execution(
        execution_id=execution_id,
        approver_id=str(current_user.id),
        approved=request.approved,
        note=request.note,
    )

    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="playbook",
        action_type="approve" if request.approved else "reject",
        action_desc=f"{'通过' if request.approved else '拒绝'}预案审批: {execution.execution_no}",
        target_type="playbook_execution",
        target_id=execution_id,
        target_name=execution.execution_no,
        severity_level="info" if request.approved else "warning",
    )

    return {
        "code": 200,
        "message": f"预案已{'通过' if request.approved else '拒绝'}",
        "data": {"status": execution.status},
    }
