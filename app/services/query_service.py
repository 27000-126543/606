from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
import os
import uuid
import csv
import json
from decimal import Decimal
from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import async_session_maker, sync_engine
from ..models.anomaly import Anomaly
from ..models.ticket import WorkOrder
from ..models.log import RawLog
from ..models.audit import AuditLog
from ..config import settings
from ..utils.logger import logger


class QueryService:
    def __init__(self):
        self._export_dir = settings.REPORT_EXPORT_DIR

    async def query_anomalies(
        self,
        system_name: Optional[str] = None,
        anomaly_type: Optional[str] = None,
        severity: Optional[List[str]] = None,
        status: Optional[List[str]] = None,
        impact_scope: Optional[str] = None,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        keyword: Optional[str] = None,
        team_ids: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        sort_by: str = "detected_time",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Anomaly], int, Dict[str, Any]]:
        async with async_session_maker() as db:
            conditions = []

            if team_ids is not None or user_id is not None:
                wo_conditions = []
                if team_ids:
                    wo_conditions.append(WorkOrder.assigned_team_id.in_(team_ids))
                if user_id:
                    wo_conditions.append(WorkOrder.assignee_id == user_id)
                
                if wo_conditions:
                    wo_subquery = select(WorkOrder.anomaly_id).where(or_(*wo_conditions))
                else:
                    wo_subquery = select(WorkOrder.anomaly_id).where(or_(False, False))
                
                conditions.append(Anomaly.id.in_(wo_subquery))
            if system_name:
                conditions.append(Anomaly.system_name == system_name)
            if anomaly_type:
                conditions.append(Anomaly.anomaly_type == anomaly_type)
            if severity:
                conditions.append(Anomaly.severity.in_(severity))
            if status:
                conditions.append(Anomaly.status.in_(status))
            if impact_scope:
                conditions.append(Anomaly.impact_scope == impact_scope)
            if time_start:
                conditions.append(Anomaly.detected_time >= time_start)
            if time_end:
                conditions.append(Anomaly.detected_time <= time_end)
            if keyword:
                keyword_like = f"%{keyword}%"
                conditions.append(
                    or_(
                        Anomaly.title.ilike(keyword_like),
                        Anomaly.description.ilike(keyword_like),
                        Anomaly.anomaly_code.ilike(keyword_like),
                    )
                )

            count_stmt = select(func.count(Anomaly.id)).where(and_(*conditions)) if conditions else select(func.count(Anomaly.id))
            total_result = await db.execute(count_stmt)
            total = int(total_result.scalar() or 0)

            sort_column = getattr(Anomaly, sort_by, Anomaly.detected_time)
            sort_expr = desc(sort_column) if sort_order == "desc" else sort_column

            query_stmt = (
                select(Anomaly)
                .where(and_(*conditions) if conditions else True)
                .order_by(sort_expr)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            result = await db.execute(query_stmt)
            anomalies = list(result.scalars().all())

            stats_stmt = (
                select(
                    func.count(Anomaly.id),
                    func.sum(Anomaly.severity == "critical"),
                    func.sum(Anomaly.severity == "high"),
                    func.sum(Anomaly.status == "open"),
                )
                .where(and_(*conditions) if conditions else True)
            )
            stats_result = await db.execute(stats_stmt)
            stats_row = stats_result.fetchone()
            stats = {
                "total": total,
                "critical": int(stats_row[1] or 0) if stats_row else 0,
                "high": int(stats_row[2] or 0) if stats_row else 0,
                "open": int(stats_row[3] or 0) if stats_row else 0,
            }

            return anomalies, total, stats

    async def query_work_orders(
        self,
        assigned_team_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        user_teams: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        anomaly_id: Optional[str] = None,
        priority: Optional[List[str]] = None,
        severity: Optional[List[str]] = None,
        status: Optional[List[str]] = None,
        is_escalated: Optional[bool] = None,
        sla_breach: Optional[bool] = None,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        keyword: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[WorkOrder], int, Dict[str, Any]]:
        async with async_session_maker() as db:
            conditions = []

            if user_teams is not None or user_id is not None:
                permission_conditions = []
                if user_teams:
                    permission_conditions.append(WorkOrder.assigned_team_id.in_(user_teams))
                if user_id:
                    permission_conditions.append(WorkOrder.assignee_id == user_id)
                
                if permission_conditions:
                    conditions.append(or_(*permission_conditions))
                else:
                    conditions.append(or_(False, False))
            if assigned_team_id:
                conditions.append(WorkOrder.assigned_team_id == assigned_team_id)
            if assignee_id:
                conditions.append(WorkOrder.assignee_id == assignee_id)
            if anomaly_id:
                conditions.append(WorkOrder.anomaly_id == anomaly_id)
            if priority:
                conditions.append(WorkOrder.priority.in_(priority))
            if severity:
                conditions.append(WorkOrder.severity.in_(severity))
            if status:
                conditions.append(WorkOrder.status.in_(status))
            if is_escalated is not None:
                conditions.append(WorkOrder.is_escalated == is_escalated)
            if sla_breach:
                conditions.append(
                    and_(
                        WorkOrder.sla_deadline.isnot(None),
                        WorkOrder.resolved_at.isnot(None),
                        WorkOrder.resolved_at > WorkOrder.sla_deadline,
                    )
                )
            if time_start:
                conditions.append(WorkOrder.created_at >= time_start)
            if time_end:
                conditions.append(WorkOrder.created_at <= time_end)
            if keyword:
                keyword_like = f"%{keyword}%"
                conditions.append(
                    or_(
                        WorkOrder.order_no.ilike(keyword_like),
                        WorkOrder.title.ilike(keyword_like),
                        WorkOrder.description.ilike(keyword_like),
                    )
                )

            count_stmt = select(func.count(WorkOrder.id)).where(and_(*conditions)) if conditions else select(func.count(WorkOrder.id))
            total_result = await db.execute(count_stmt)
            total = int(total_result.scalar() or 0)

            sort_column = getattr(WorkOrder, sort_by, WorkOrder.created_at)
            sort_expr = desc(sort_column) if sort_order == "desc" else sort_column

            query_stmt = (
                select(WorkOrder)
                .where(and_(*conditions) if conditions else True)
                .order_by(sort_expr)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            result = await db.execute(query_stmt)
            orders = list(result.scalars().all())

            sla_breach_count = 0
            if total > 0:
                breach_stmt = select(func.count(WorkOrder.id)).where(
                    and_(
                        *conditions,
                        WorkOrder.sla_deadline.isnot(None),
                        or_(
                            and_(WorkOrder.status.in_(["pending", "assigned", "in_progress"]),
                                 WorkOrder.sla_deadline < datetime.now(timezone.utc)),
                            and_(WorkOrder.resolved_at.isnot(None),
                                 WorkOrder.resolved_at > WorkOrder.sla_deadline),
                        ),
                    )
                )
                breach_result = await db.execute(breach_stmt)
                sla_breach_count = int(breach_result.scalar() or 0)

            stats = {
                "total": total,
                "pending": sum(1 for o in orders if o.status == "pending"),
                "in_progress": sum(1 for o in orders if o.status in ("assigned", "in_progress", "verifying")),
                "completed": sum(1 for o in orders if o.status in ("completed", "closed")),
                "sla_breach": sla_breach_count,
                "escalated": sum(1 for o in orders if o.is_escalated),
            }

            return orders, total, stats

    async def query_logs(
        self,
        system_name: Optional[str] = None,
        log_level: Optional[List[str]] = None,
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
    ) -> Tuple[List[RawLog], int, Dict[str, Any]]:
        async with async_session_maker() as db:
            conditions = []

            if system_name:
                conditions.append(RawLog.system_name == system_name)
            if log_level:
                conditions.append(RawLog.log_level.in_(log_level))
            if module:
                conditions.append(RawLog.module == module)
            if trace_id:
                conditions.append(RawLog.trace_id == trace_id)
            if host_ip:
                conditions.append(RawLog.host_ip == host_ip)
            if time_start:
                conditions.append(RawLog.log_time >= time_start)
            if time_end:
                conditions.append(RawLog.log_time <= time_end)
            if keyword:
                keyword_like = f"%{keyword}%"
                conditions.append(RawLog.message.ilike(keyword_like))

            count_stmt = select(func.count(RawLog.id)).where(and_(*conditions)) if conditions else select(func.count(RawLog.id))
            total_result = await db.execute(count_stmt)
            total = int(total_result.scalar() or 0)

            sort_column = getattr(RawLog, sort_by, RawLog.log_time)
            sort_expr = desc(sort_column) if sort_order == "desc" else sort_column

            query_stmt = (
                select(RawLog)
                .where(and_(*conditions) if conditions else True)
                .order_by(sort_expr)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            result = await db.execute(query_stmt)
            logs = list(result.scalars().all())

            level_counts = {}
            if total > 0:
                level_stmt = (
                    select(RawLog.log_level, func.count(RawLog.id))
                    .where(and_(*conditions) if conditions else True)
                    .group_by(RawLog.log_level)
                )
                level_result = await db.execute(level_stmt)
                for level, count in level_result.fetchall():
                    level_counts[level] = int(count)

            stats = {
                "total": total,
                "level_distribution": level_counts,
            }

            return logs, total, stats

    async def export_anomalies_csv(
        self, **query_params
    ) -> str:
        query_params.pop("page", None)
        query_params.pop("page_size", None)

        anomalies, _, _ = await self.query_anomalies(
            **query_params,
            page=1,
            page_size=100000,
        )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"anomalies_export_{timestamp}.csv"
        filepath = os.path.join(self._export_dir, filename)

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "异常编号", "系统名称", "异常类型", "严重等级", "标题",
                "状态", "影响范围", "影响评分", "检测时间", "首次发生", "最后发生",
                "发生次数", "解决时间", "解决方式", "置信度", "算法",
            ])

            for a in anomalies:
                writer.writerow([
                    a.anomaly_code,
                    a.system_name,
                    a.anomaly_type,
                    a.severity,
                    a.title,
                    a.status,
                    a.impact_scope,
                    str(a.impact_score) if a.impact_score else "",
                    a.detected_time.isoformat() if a.detected_time else "",
                    a.first_occurrence_time.isoformat() if a.first_occurrence_time else "",
                    a.last_occurrence_time.isoformat() if a.last_occurrence_time else "",
                    a.occurrence_count,
                    a.resolved_time.isoformat() if a.resolved_time else "",
                    a.resolution_method or "",
                    str(a.confidence) if a.confidence else "",
                    a.detection_algorithm or "",
                ])

        logger.info(f"Exported {len(anomalies)} anomalies to {filepath}")
        return filepath

    async def export_work_orders_csv(
        self, **query_params
    ) -> str:
        query_params.pop("page", None)
        query_params.pop("page_size", None)

        orders, _, _ = await self.query_work_orders(
            **query_params,
            page=1,
            page_size=100000,
        )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"work_orders_export_{timestamp}.csv"
        filepath = os.path.join(self._export_dir, filename)

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "工单编号", "关联异常", "标题", "优先级", "严重等级",
                "状态", "影响范围", "是否升级", "升级次数",
                "创建时间", "首次响应", "开始处理", "解决时间",
                "SLA截止", "实际修复时长(分钟)", "催办次数",
            ])

            for o in orders:
                writer.writerow([
                    o.order_no,
                    str(o.anomaly_id),
                    o.title,
                    o.priority,
                    o.severity,
                    o.status,
                    o.impact_scope,
                    "是" if o.is_escalated else "否",
                    o.escalation_count,
                    o.created_at.isoformat() if o.created_at else "",
                    o.first_response_at.isoformat() if o.first_response_at else "",
                    o.started_at.isoformat() if o.started_at else "",
                    o.resolved_at.isoformat() if o.resolved_at else "",
                    o.sla_deadline.isoformat() if o.sla_deadline else "",
                    o.actual_resolution_minutes or "",
                    o.reminder_count,
                ])

        logger.info(f"Exported {len(orders)} work orders to {filepath}")
        return filepath

    async def export_logs_csv(
        self, **query_params
    ) -> str:
        query_params.pop("page", None)
        query_params.pop("page_size", None)

        logs, _, _ = await self.query_logs(
            **query_params,
            page=1,
            page_size=500000,
        )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"logs_export_{timestamp}.csv"
        filepath = os.path.join(self._export_dir, filename)

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "日志ID", "系统名称", "主机IP", "日志级别", "模块",
                "Trace ID", "日志时间", "接收时间", "消息内容",
            ])

            for log in logs:
                writer.writerow([
                    str(log.log_id),
                    log.system_name,
                    log.host_ip or "",
                    log.log_level,
                    log.module or "",
                    log.trace_id or "",
                    log.log_time.isoformat() if log.log_time else "",
                    log.receive_time.isoformat() if log.receive_time else "",
                    (log.message or "").replace("\n", " ").replace("\r", " ")[:2000],
                ])

        logger.info(f"Exported {len(logs)} logs to {filepath}")
        return filepath

    async def export_json(
        self,
        data_type: str,
        items: List[Any],
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{data_type}_export_{timestamp}.json"
        filepath = os.path.join(self._export_dir, filename)

        def _default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, (uuid.UUID, Decimal)):
                return str(obj)
            if hasattr(obj, "__dict__"):
                return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
            return str(obj)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                items,
                f,
                ensure_ascii=False,
                indent=2,
                default=_default_serializer,
            )

        logger.info(f"Exported {len(items)} {data_type} records to JSON: {filepath}")
        return filepath


query_service = QueryService()
