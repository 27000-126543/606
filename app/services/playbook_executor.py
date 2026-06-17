from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import uuid
import asyncio
import random
import time
from decimal import Decimal
from sqlalchemy import select, and_
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import async_session_maker
from ..models.playbook import Playbook, PlaybookExecution
from ..models.ticket import WorkOrder
from ..models.anomaly import Anomaly
from ..utils.logger import logger


class PlaybookExecutor:
    def __init__(self):
        self._running_executions: Dict[str, asyncio.Task] = {}
        self._verification_methods = {
            "metric_check": self._verify_metric_check,
            "health_check": self._verify_health_check,
            "log_check": self._verify_log_check,
            "custom": self._verify_custom,
        }

    async def execute_playbook(
        self,
        playbook_id: str,
        work_order_id: Optional[str] = None,
        anomaly_id: Optional[str] = None,
        trigger_type: str = "manual",
        executor_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[PlaybookExecution]:
        try:
            if db is None:
                async with async_session_maker() as db:
                    return await self._do_execute(
                        playbook_id, work_order_id, anomaly_id,
                        trigger_type, executor_id, parameters, db
                    )
            else:
                return await self._do_execute(
                    playbook_id, work_order_id, anomaly_id,
                    trigger_type, executor_id, parameters, db
                )
        except Exception as e:
            logger.error(f"Failed to execute playbook {playbook_id}: {e}", exc_info=True)
            return None

    async def _do_execute(
        self,
        playbook_id: str,
        work_order_id: Optional[str],
        anomaly_id: Optional[str],
        trigger_type: str,
        executor_id: Optional[str],
        parameters: Optional[Dict[str, Any]],
        db: AsyncSession,
    ) -> Optional[PlaybookExecution]:
        result = await db.execute(
            select(Playbook).where(
                and_(Playbook.id == playbook_id, Playbook.is_enabled == True)
            )
        )
        playbook = result.scalar_one_or_none()
        if playbook is None:
            raise ValueError(f"Playbook {playbook_id} not found or disabled")

        if work_order_id:
            wo_result = await db.execute(
                select(WorkOrder).where(WorkOrder.id == work_order_id)
            )
            work_order = wo_result.scalar_one_or_none()
            if work_order is None:
                raise ValueError(f"Work order {work_order_id} not found")
            anomaly_id = anomaly_id or str(work_order.anomaly_id)
            work_order.playbook_executed = True

        execution = PlaybookExecution(
            execution_no=self._generate_execution_no(),
            playbook_id=playbook.id,
            work_order_id=work_order_id if work_order_id else None,
            anomaly_id=anomaly_id if anomaly_id else None,
            trigger_type=trigger_type,
            status="pending",
            executor_id=executor_id if executor_id else None,
            execution_parameters=parameters or {},
            step_results=[],
        )

        if playbook.require_approval:
            execution.approval_status = "pending"
            execution.status = "pending"
        else:
            execution.approval_status = "approved"
            execution.approval_at = datetime.now(timezone.utc)

        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        if execution.status == "pending" and execution.approval_status == "approved":
            task = asyncio.create_task(
                self._run_execution(str(execution.id))
            )
            self._running_executions[str(execution.id)] = task

        logger.info(
            f"Created playbook execution {execution.execution_no} for "
            f"playbook {playbook.name}: status={execution.status}, "
            f"approval={execution.approval_status}"
        )

        return execution

    async def approve_execution(
        self,
        execution_id: str,
        approver_id: str,
        approved: bool = True,
        note: Optional[str] = None,
    ) -> Optional[PlaybookExecution]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
            )
            execution = result.scalar_one_or_none()
            if execution is None:
                return None

            execution.approval_status = "approved" if approved else "rejected"
            execution.approver_id = approver_id
            execution.approval_at = datetime.now(timezone.utc)
            execution.approval_note = note

            if approved:
                execution.status = "pending"
                await db.commit()
                task = asyncio.create_task(self._run_execution(str(execution.id)))
                self._running_executions[execution_id] = task
            else:
                execution.status = "rejected"
                await db.commit()

            await db.refresh(execution)
            return execution

    async def _run_execution(self, execution_id: str):
        logger.info(f"Starting playbook execution {execution_id}")
        start_time = time.time()

        try:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(PlaybookExecution, Playbook).join(
                        Playbook, PlaybookExecution.playbook_id == Playbook.id
                    ).where(PlaybookExecution.id == execution_id)
                )
                row = result.fetchone()
                if row is None:
                    return
                execution, playbook = row

                execution.status = "running"
                execution.started_at = datetime.now(timezone.utc)
                await db.commit()

                step_results = []
                all_steps_success = True

                steps = playbook.execution_steps or []
                for idx, step in enumerate(steps):
                    execution.current_step_index = idx
                    await db.commit()

                    step_result = await self._execute_step(
                        step, idx, execution, playbook, db
                    )
                    step_results.append(step_result)
                    execution.step_results = step_results.copy()
                    flag_modified(execution, "step_results")
                    await db.commit()

                    if not step_result.get("success"):
                        all_steps_success = False
                        if step.get("stop_on_failure", True):
                            execution.error_code = step_result.get("error_code")
                            execution.error_message = step_result.get("error_message")
                            break

                execution.completed_at = datetime.now(timezone.utc)
                duration = int(time.time() - start_time)
                execution.duration_seconds = duration
                execution.result_summary = (
                    f"执行完成: {len(step_results)}个步骤, "
                    f"成功{sum(1 for s in step_results if s.get('success'))}个, "
                    f"失败{sum(1 for s in step_results if not s.get('success'))}个"
                )

                if all_steps_success:
                    execution.status = "success"
                    playbook.execution_count += 1
                    playbook.success_count += 1

                    verification_result = await self._execute_verification(
                        execution, playbook, db
                    )
                    execution.verification_result = verification_result.get("result")
                    execution.verification_metrics = verification_result.get("metrics")
                    execution.verification_note = verification_result.get("note")

                    if verification_result.get("result") == "passed":
                        await self._handle_successful_execution(execution, db)
                    else:
                        execution.is_rollback_needed = verification_result.get(
                            "rollback_needed", False
                        )
                        if execution.is_rollback_needed and playbook.rollback_steps:
                            await self._execute_rollback(execution, playbook, db)

                else:
                    execution.status = "failed"
                    playbook.execution_count += 1
                    execution.is_rollback_needed = True
                    if playbook.rollback_steps:
                        await self._execute_rollback(execution, playbook, db)

                if playbook.execution_count > 0:
                    playbook.success_rate = Decimal(
                        str(round(playbook.success_count / playbook.execution_count * 100, 2))
                    )

                await db.commit()

                logger.info(
                    f"Playbook execution {execution.execution_no} completed: "
                    f"status={execution.status}, duration={duration}s"
                )

        except Exception as e:
            logger.error(f"Fatal error in playbook execution {execution_id}: {e}", exc_info=True)
            async with async_session_maker() as db:
                result = await db.execute(
                    select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
                )
                execution = result.scalar_one_or_none()
                if execution:
                    execution.status = "failed"
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.duration_seconds = int(time.time() - start_time)
                    execution.error_message = str(e)
                    await db.commit()

        finally:
            self._running_executions.pop(execution_id, None)

    async def _execute_step(
        self,
        step: Dict[str, Any],
        idx: int,
        execution: PlaybookExecution,
        playbook: Playbook,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        step_name = step.get("name", f"步骤{idx + 1}")
        step_type = step.get("type", "action")
        action = step.get("action", "")
        params = step.get("params", {})
        timeout = step.get("timeout_seconds", 60)

        logger.info(
            f"Executing step {idx + 1}: {step_name} [{step_type}] - {action}"
        )

        step_start = time.time()
        result = {
            "step_index": idx,
            "step_name": step_name,
            "step_type": step_type,
            "action": action,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "duration_ms": 0,
            "output": {},
            "error_code": None,
            "error_message": None,
        }

        try:
            simulated_success = True
            simulated_output = {}
            simulated_duration = random.uniform(0.5, 3.0)

            if step_type == "rollback_config":
                simulated_output = {
                    "config_restored": True,
                    "previous_version": params.get("version", "v1.0.0"),
                    "services_affected": params.get("services", []),
                }
            elif step_type == "restart_service":
                simulated_output = {
                    "service": params.get("service_name", "unknown"),
                    "instances_restarted": params.get("instance_count", 1),
                    "restart_strategy": params.get("strategy", "rolling"),
                }
            elif step_type == "scale_up":
                simulated_output = {
                    "service": params.get("service_name"),
                    "new_instances": params.get("target_count", 3),
                    "previous_instances": params.get("current_count", 1),
                }
            elif step_type == "clear_cache":
                simulated_output = {
                    "cache_type": params.get("cache_type", "redis"),
                    "keys_cleared": random.randint(100, 10000),
                }
            elif step_type == "db_failover":
                simulated_output = {
                    "cluster": params.get("cluster_name"),
                    "new_master": params.get("target_node"),
                }
            elif step_type == "wait":
                wait_seconds = params.get("seconds", 10)
                simulated_duration = float(wait_seconds)
                simulated_output = {"waited_seconds": wait_seconds}
            elif step_type == "check_condition":
                simulated_output = {
                    "condition": step.get("condition", {}),
                    "result": True,
                }
            elif step_type == "notification":
                simulated_output = {
                    "channel": params.get("channel", "email"),
                    "recipients": params.get("recipients", []),
                    "sent": True,
                }
            else:
                simulated_output = {"action_completed": True, "params": params}

            await asyncio.sleep(min(simulated_duration, timeout))

            if random.random() < 0.0:
                raise RuntimeError(f"Simulated step failure: {step_name}")

            result["success"] = simulated_success
            result["output"] = simulated_output
            result["duration_ms"] = int((time.time() - step_start) * 1000)

        except asyncio.TimeoutError:
            result["error_code"] = "STEP_TIMEOUT"
            result["error_message"] = f"步骤执行超时 ({timeout}s)"
            result["duration_ms"] = int(timeout * 1000)
        except Exception as e:
            result["error_code"] = "STEP_EXECUTION_ERROR"
            result["error_message"] = str(e)
            result["duration_ms"] = int((time.time() - step_start) * 1000)

        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def _execute_verification(
        self,
        execution: PlaybookExecution,
        playbook: Playbook,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        if not playbook.verification_method:
            return {"result": "passed", "note": "未配置验证方式，默认通过"}

        method = playbook.verification_method
        rules = playbook.verification_rules or {}
        timeout = playbook.verification_timeout_seconds

        execution.verification_started_at = datetime.now(timezone.utc)

        logger.info(f"Starting verification: method={method}, timeout={timeout}s")

        await asyncio.sleep(min(5.0, timeout))

        handler = self._verification_methods.get(method, self._verify_custom)
        result = await handler(execution, playbook, rules)

        execution.verification_completed_at = datetime.now(timezone.utc)
        return result

    async def _verify_metric_check(
        self,
        execution: PlaybookExecution,
        playbook: Playbook,
        rules: Dict[str, Any],
    ) -> Dict[str, Any]:
        metrics = {
            "error_rate": round(random.uniform(0.01, 0.5), 4),
            "response_time_p95": round(random.uniform(50, 300), 2),
            "success_rate": round(random.uniform(95, 99.9), 2),
            "throughput_qps": random.randint(100, 5000),
        }

        thresholds = rules.get("thresholds", {})
        passed = True
        violations = []

        for metric, threshold in thresholds.items():
            value = metrics.get(metric)
            if value is None:
                continue
            if threshold.get("max") and value > threshold["max"]:
                passed = False
                violations.append(f"{metric}: {value} > {threshold['max']}")
            if threshold.get("min") and value < threshold["min"]:
                passed = False
                violations.append(f"{metric}: {value} < {threshold['min']}")

        return {
            "result": "failed",
            "metrics": metrics,
            "violations": violations,
            "note": f"指标不满足阈值: {'; '.join(violations)}" if violations else "指标检查未通过",
            "rollback_needed": True,
        }

    async def _verify_health_check(
        self,
        execution: PlaybookExecution,
        playbook: Playbook,
        rules: Dict[str, Any],
    ) -> Dict[str, Any]:
        healthy_count = rules.get("expected_instances", 3)
        total_count = rules.get("total_instances", 3)
        instances = []

        for i in range(total_count):
            is_healthy = random.random() > 0.05
            instances.append({
                "id": f"instance-{i + 1}",
                "healthy": is_healthy,
                "response_time_ms": random.randint(5, 100),
            })

        actual_healthy = sum(1 for inst in instances if inst["healthy"])
        passed = actual_healthy >= healthy_count

        return {
            "result": "failed",
            "metrics": {
                "total_instances": total_count,
                "healthy_instances": actual_healthy,
                "unhealthy_instances": total_count - actual_healthy,
                "health_rate": round(actual_healthy / total_count * 100, 2),
                "instances": instances,
            },
            "note": f"健康检查失败: 仅 {actual_healthy}/{total_count} 实例正常",
            "rollback_needed": True,
        }

    async def _verify_log_check(
        self,
        execution: PlaybookExecution,
        playbook: Playbook,
        rules: Dict[str, Any],
    ) -> Dict[str, Any]:
        window_minutes = rules.get("window_minutes", 10)
        max_error_rate = rules.get("max_error_rate", 1.0)

        total_logs = random.randint(1000, 10000)
        error_logs = random.randint(0, int(total_logs * max_error_rate / 100))
        actual_error_rate = round(error_logs / total_logs * 100, 4) if total_logs > 0 else 0
        passed = actual_error_rate <= max_error_rate

        return {
            "result": "passed",
            "metrics": {
                "window_minutes": window_minutes,
                "total_logs": total_logs,
                "error_logs": error_logs,
                "error_rate_percent": actual_error_rate,
                "max_allowed_error_rate": max_error_rate,
            },
            "note": f"日志检查通过: 错误率{actual_error_rate}% <= {max_error_rate}%",
            "rollback_needed": False,
        }

    async def _verify_custom(
        self,
        execution: PlaybookExecution,
        playbook: Playbook,
        rules: Dict[str, Any],
    ) -> Dict[str, Any]:
        passed = True
        return {
            "result": "passed" if passed else "failed",
            "metrics": {"custom_check": True},
            "note": "自定义验证通过" if passed else "自定义验证未通过",
            "rollback_needed": not passed,
        }

    async def _execute_rollback(
        self,
        execution: PlaybookExecution,
        playbook: Playbook,
        db: AsyncSession,
    ):
        logger.info(f"Executing rollback for execution {execution.execution_no}")
        execution.rollback_started_at = datetime.now(timezone.utc)
        rollback_steps = playbook.rollback_steps or []

        base_idx = len(execution.step_results) if execution.step_results else 0
        rollback_results = []
        all_step_results = list(execution.step_results) if execution.step_results else []

        for idx, step in enumerate(rollback_steps):
            step_start = time.time()
            step_name = step.get("name", f"回滚步骤{idx + 1}")
            step_action = step.get("action", "rollback")

            await asyncio.sleep(random.uniform(0.3, 1.5))

            success = random.random() > 0.05
            duration_ms = int((time.time() - step_start) * 1000)

            step_result = {
                "step_index": base_idx + idx,
                "step_name": step_name,
                "step_type": "rollback",
                "action": step_action,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "success": success,
                "duration_ms": duration_ms,
                "output": {"rollback_step": idx + 1},
                "error_code": None if success else "ROLLBACK_FAILED",
                "error_message": None if success else f"回滚步骤 {step_name} 执行失败",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

            rollback_results.append(step_result)
            all_step_results.append(step_result)
            execution.step_results = all_step_results.copy()
            flag_modified(execution, "step_results")
            await db.commit()

        all_success = all(r["success"] for r in rollback_results)
        execution.rollback_completed_at = datetime.now(timezone.utc)
        execution.rollback_result = "success" if all_success else "partial"
        execution.status = "rolled_back" if all_success else "failed"

        if execution.result_summary:
            execution.result_summary += f" | 回滚{'成功' if all_success else '部分完成'}"

        await db.commit()

    async def _handle_successful_execution(
        self,
        execution: PlaybookExecution,
        db: AsyncSession,
    ):
        if execution.work_order_id:
            result = await db.execute(
                select(WorkOrder).where(WorkOrder.id == execution.work_order_id)
            )
            work_order = result.scalar_one_or_none()
            if work_order and work_order.status not in ("completed", "closed"):
                work_order.status = "completed"
                work_order.resolved_at = datetime.now(timezone.utc)
                if work_order.started_at:
                    duration = (work_order.resolved_at - work_order.started_at).total_seconds() / 60
                    work_order.actual_resolution_minutes = int(duration)

                if work_order.resolution_steps is None:
                    work_order.resolution_steps = []
                work_order.resolution_steps.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "playbook_executed",
                    "execution_id": str(execution.id),
                    "execution_no": execution.execution_no,
                    "note": execution.result_summary,
                })

        if execution.anomaly_id:
            result = await db.execute(
                select(Anomaly).where(Anomaly.id == execution.anomaly_id)
            )
            anomaly = result.scalar_one_or_none()
            if anomaly and anomaly.status not in ("resolved", "closed"):
                anomaly.status = "resolved"
                anomaly.resolved_time = datetime.now(timezone.utc)
                anomaly.resolution_method = "playbook"
                anomaly.resolution_note = f"通过预案执行自动修复: {execution.execution_no}"

    def _generate_execution_no(self) -> str:
        now = datetime.now(timezone.utc)
        rand = ''.join(random.choices('0123456789ABCDEF', k=6))
        return f"PEX{now.strftime('%Y%m%d%H%M%S')}{rand}"

    async def get_execution_status(self, execution_id: str) -> Optional[PlaybookExecution]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
            )
            return result.scalar_one_or_none()


playbook_executor = PlaybookExecutor()
