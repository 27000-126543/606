from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import uuid
from functools import wraps
from fastapi import Request
from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import async_session_maker
from ..models.audit import AuditLog
from ..models.user import User
from ..utils.logger import logger


class AuditService:
    def __init__(self):
        pass

    async def log_action(
        self,
        user_id: Optional[str],
        username: Optional[str],
        module: str,
        action_type: str,
        action_desc: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        target_name: Optional[str] = None,
        before_value: Optional[Any] = None,
        after_value: Optional[Any] = None,
        changed_fields: Optional[List[str]] = None,
        request_data: Optional[Any] = None,
        response_data: Optional[Any] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        system_name: Optional[str] = None,
        anomaly_id: Optional[str] = None,
        work_order_id: Optional[str] = None,
        severity_level: str = "info",
        user_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        execution_duration_ms: Optional[int] = None,
        trace_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AuditLog]:
        async def _save(db_session):
            try:
                log_entry = AuditLog(
                    user_id=uuid.UUID(user_id) if user_id else None,
                    username=username,
                    user_ip=user_ip,
                    user_agent=user_agent,
                    module=module,
                    action_type=action_type,
                    action_desc=action_desc,
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name,
                    before_value=self._serialize(before_value),
                    after_value=self._serialize(after_value),
                    changed_fields=changed_fields,
                    request_data=self._serialize(request_data),
                    response_data=self._serialize(response_data),
                    status=status,
                    error_message=error_message,
                    system_name=system_name,
                    anomaly_id=uuid.UUID(anomaly_id) if anomaly_id else None,
                    work_order_id=uuid.UUID(work_order_id) if work_order_id else None,
                    severity_level=severity_level,
                    execution_duration_ms=execution_duration_ms,
                    trace_id=trace_id,
                    extra_metadata=self._serialize(extra_metadata),
                )
                db_session.add(log_entry)
                await db_session.commit()
                await db_session.refresh(log_entry)
                return log_entry
            except Exception as e:
                logger.error(f"Failed to save audit log: {e}", exc_info=True)
                return None

        if db is None:
            async with async_session_maker() as db:
                return await _save(db)
        else:
            return await _save(db)

    def _serialize(self, value: Any) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        try:
            if isinstance(value, (dict, list, str, int, float, bool)):
                return value
            if hasattr(value, "__dict__"):
                return {k: str(v) for k, v in value.__dict__.items() if not k.startswith("_")}
            return str(value)
        except Exception:
            return str(value)

    async def query_audit_logs(
        self,
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
    ) -> Tuple[List[AuditLog], int]:
        async with async_session_maker() as db:
            conditions = []

            if user_id:
                conditions.append(AuditLog.user_id == user_id)
            if module:
                conditions.append(AuditLog.module == module)
            if action_type:
                conditions.append(AuditLog.action_type == action_type)
            if target_type:
                conditions.append(AuditLog.target_type == target_type)
            if target_id:
                conditions.append(AuditLog.target_id == target_id)
            if system_name:
                conditions.append(AuditLog.system_name == system_name)
            if anomaly_id:
                conditions.append(AuditLog.anomaly_id == anomaly_id)
            if work_order_id:
                conditions.append(AuditLog.work_order_id == work_order_id)
            if severity_level:
                conditions.append(AuditLog.severity_level == severity_level)
            if status:
                conditions.append(AuditLog.status == status)
            if time_start:
                conditions.append(AuditLog.action_time >= time_start)
            if time_end:
                conditions.append(AuditLog.action_time <= time_end)
            if keyword:
                keyword_like = f"%{keyword}%"
                conditions.append(
                    or_(
                        AuditLog.action_desc.ilike(keyword_like),
                        AuditLog.username.ilike(keyword_like),
                        AuditLog.target_name.ilike(keyword_like),
                    )
                )

            count_stmt = select(func.count(AuditLog.id)).where(and_(*conditions)) if conditions else select(func.count(AuditLog.id))
            total_result = await db.execute(count_stmt)
            total = int(total_result.scalar() or 0)

            query_stmt = (
                select(AuditLog)
                .where(and_(*conditions) if conditions else True)
                .order_by(desc(AuditLog.action_time))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            result = await db.execute(query_stmt)
            logs = list(result.scalars().all())

            return logs, total

    async def batch_export_audit_logs(
        self,
        **query_params,
    ) -> List[Dict[str, Any]]:
        query_params.pop("page", None)
        query_params.pop("page_size", None)

        logs, _ = await self.query_audit_logs(
            **query_params,
            page=1,
            page_size=100000,
        )

        return [self._audit_to_dict(log) for log in logs]

    def _audit_to_dict(self, log: AuditLog) -> Dict[str, Any]:
        return {
            "id": str(log.audit_id),
            "user_id": str(log.user_id) if log.user_id else None,
            "username": log.username,
            "user_ip": log.user_ip,
            "module": log.module,
            "action_type": log.action_type,
            "action_desc": log.action_desc,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "target_name": log.target_name,
            "status": log.status,
            "error_message": log.error_message,
            "system_name": log.system_name,
            "anomaly_id": str(log.anomaly_id) if log.anomaly_id else None,
            "work_order_id": str(log.work_order_id) if log.work_order_id else None,
            "severity_level": log.severity_level,
            "action_time": log.action_time.isoformat() if log.action_time else None,
            "execution_duration_ms": log.execution_duration_ms,
            "trace_id": log.trace_id,
        }


audit_service = AuditService()


def audit_action(
    module: str,
    action_type: str,
    target_type: Optional[str] = None,
    severity_level: str = "info",
    include_request: bool = True,
    include_response: bool = True,
):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            import time
            request: Optional[Request] = kwargs.get("request")
            current_user: Optional[User] = kwargs.get("current_user")

            user_id = str(current_user.id) if current_user else None
            username = current_user.username if current_user else None
            user_ip = None
            user_agent = None

            if request:
                user_ip = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")

            target_id = None
            target_name_val = None
            for key in ["id", "anomaly_id", "work_order_id", "ticket_id", "order_id"]:
                if key in kwargs:
                    target_id = str(kwargs[key])
                    break

            start_time = time.time()
            status = "success"
            error_msg = None
            result = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "failed"
                error_msg = str(e)
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)

                action_desc = f"{module} - {action_type}"
                if hasattr(result, "__dict__") and "name" in result.__dict__:
                    target_name_val = result.__dict__["name"]

                await audit_service.log_action(
                    user_id=user_id,
                    username=username,
                    module=module,
                    action_type=action_type,
                    action_desc=action_desc,
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name_val,
                    request_data=kwargs if include_request else None,
                    response_data=result if include_response and not isinstance(result, bytes) else None,
                    status=status,
                    error_message=error_msg,
                    severity_level=severity_level if status == "success" else "danger",
                    user_ip=user_ip,
                    user_agent=user_agent,
                    execution_duration_ms=duration_ms,
                )

        return wrapper
    return decorator
