from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import uuid
import random
from decimal import Decimal
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import async_session_maker
from ..models.anomaly import Anomaly
from ..models.ticket import WorkOrder, FollowUpTask
from ..models.user import User, Team, UserTeam
from ..models.playbook import Playbook
from ..utils.logger import logger


class TicketService:
    def __init__(self):
        self._sla_configs = {
            "P0": {"response_minutes": 5, "resolution_minutes": 60},
            "P1": {"response_minutes": 15, "resolution_minutes": 240},
            "P2": {"response_minutes": 60, "resolution_minutes": 480},
            "P3": {"response_minutes": 240, "resolution_minutes": 1440},
            "P4": {"response_minutes": 1440, "resolution_minutes": 4320},
        }
        self._escalation_interval_hours = 4

    async def create_work_order_for_anomaly(
        self, anomaly_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[WorkOrder]:
        try:
            if db is None:
                async with async_session_maker() as db:
                    return await self._create_order(anomaly_id, db)
            else:
                return await self._create_order(anomaly_id, db)
        except Exception as e:
            logger.error(f"Failed to create work order for anomaly {anomaly_id}: {e}", exc_info=True)
            return None

    async def _create_order(
        self, anomaly_id: str, db: AsyncSession
    ) -> Optional[WorkOrder]:
        existing = await db.execute(
            select(WorkOrder).where(WorkOrder.anomaly_id == anomaly_id)
        )
        if existing.scalar_one_or_none():
            return None

        result = await db.execute(select(Anomaly).where(Anomaly.id == anomaly_id))
        anomaly = result.scalar_one_or_none()
        if anomaly is None:
            return None

        priority = self._map_severity_to_priority(anomaly.severity)
        sla = self._sla_configs.get(priority, self._sla_configs["P3"])
        sla_deadline = datetime.now(timezone.utc) + timedelta(minutes=sla["resolution_minutes"])

        assigned_team_id = await self._determine_assigned_team(anomaly, db)
        assignee_id = await self._determine_assignee(assigned_team_id, db)

        order_no = self._generate_order_no()

        work_order = WorkOrder(
            order_no=order_no,
            anomaly_id=anomaly.id,
            title=anomaly.title,
            description=anomaly.description,
            anomaly_type=anomaly.anomaly_type,
            severity=anomaly.severity,
            priority=priority,
            impact_scope=anomaly.impact_scope,
            assigned_team_id=assigned_team_id,
            assignee_id=assignee_id,
            auto_assigned=True,
            status="assigned" if assignee_id else "pending",
            sla_deadline=sla_deadline,
            first_response_at=datetime.now(timezone.utc) if assignee_id else None,
        )

        db.add(work_order)
        await db.flush()

        if anomaly.status == "open":
            anomaly.status = "investigating"

        if not assignee_id:
            await self._create_follow_up_task(work_order, db, "pending_assignment")

        severity_rank = {"critical": 0, "high": 1}
        if anomaly.severity in severity_rank:
            await self._check_auto_playbook_execution(work_order, anomaly, db)

        await db.commit()
        await db.refresh(work_order)

        logger.info(
            f"Created work order {order_no} for anomaly {anomaly.anomaly_code}: "
            f"team={assigned_team_id}, assignee={assignee_id}, priority={priority}"
        )

        return work_order

    def _map_severity_to_priority(self, severity: str) -> str:
        mapping = {
            "critical": "P0",
            "high": "P1",
            "medium": "P2",
            "low": "P3",
        }
        return mapping.get(severity.lower(), "P3")

    async def _determine_assigned_team(
        self, anomaly: Anomaly, db: AsyncSession
    ) -> uuid.UUID:
        if anomaly.root_cause_analysis and anomaly.root_cause_analysis.get("recommended_teams"):
            teams = anomaly.root_cause_analysis["recommended_teams"]
            if teams:
                try:
                    return uuid.UUID(teams[0])
                except (ValueError, TypeError):
                    pass

        stmt = select(Team).where(Team.is_active == True).order_by(Team.name)
        result = await db.execute(stmt)
        teams = result.scalars().all()

        if teams:
            system_teams = [t for t in teams if anomaly.system_name.lower() in t.name.lower()]
            if system_teams:
                return system_teams[0].id
            return teams[0].id

        default_team = Team(
            name="默认运维团队",
            description="系统自动创建的默认运维团队",
        )
        db.add(default_team)
        await db.flush()
        return default_team.id

    async def _determine_assignee(
        self, team_id: uuid.UUID, db: AsyncSession
    ) -> Optional[uuid.UUID]:
        stmt = (
            select(User, UserTeam)
            .join(UserTeam, User.id == UserTeam.user_id)
            .where(
                and_(
                    UserTeam.team_id == team_id,
                    User.is_active == True,
                )
            )
            .order_by(UserTeam.is_team_leader.desc())
        )
        result = await db.execute(stmt)
        members = result.fetchall()

        if not members:
            return None

        workload = defaultdict(int)
        for user, _ in members:
            count_result = await db.execute(
                select(func.count(WorkOrder.id)).where(
                    and_(
                        WorkOrder.assignee_id == user.id,
                        WorkOrder.status.in_(["assigned", "in_progress", "verifying"]),
                    )
                )
            )
            workload[user.id] = count_result.scalar_one() or 0

        min_workload = min(workload.values())
        candidates = [uid for uid, count in workload.items() if count == min_workload]
        return random.choice(candidates) if candidates else members[0][0].id

    def _generate_order_no(self) -> str:
        now = datetime.now(timezone.utc)
        rand = ''.join(random.choices('0123456789ABCDEF', k=6))
        return f"WO{now.strftime('%Y%m%d%H%M%S')}{rand}"

    async def _create_follow_up_task(
        self,
        work_order: WorkOrder,
        db: AsyncSession,
        task_type: str = "manual_follow_up",
    ) -> FollowUpTask:
        now = datetime.now(timezone.utc)

        if task_type == "pending_assignment":
            title = f"工单待分配跟进: {work_order.order_no}"
            description = f"工单 {work_order.order_no} 尚未分配处理人，请尽快指派。"
            priority = work_order.priority
            next_follow = now + timedelta(minutes=30)
            interval = 1
        elif task_type == "escalation":
            title = f"工单超时升级: {work_order.order_no}"
            description = f"工单 {work_order.order_no} 处理超时，已升级至主管跟进。"
            priority = "P1" if work_order.priority not in ("P0", "P1") else "P0"
            next_follow = now + timedelta(hours=self._escalation_interval_hours)
            interval = self._escalation_interval_hours
        else:
            title = f"工单跟进提醒: {work_order.order_no}"
            description = f"请及时跟进处理工单 {work_order.order_no}，SLA截止时间: {work_order.sla_deadline}"
            priority = work_order.priority
            next_follow = now + timedelta(hours=self._escalation_interval_hours)
            interval = self._escalation_interval_hours

        task = FollowUpTask(
            work_order_id=work_order.id,
            task_type=task_type,
            title=title,
            description=description,
            priority=priority,
            next_follow_up_at=next_follow,
            follow_up_interval_hours=interval,
        )
        db.add(task)
        return task

    async def _check_auto_playbook_execution(
        self, work_order: WorkOrder, anomaly: Anomaly, db: AsyncSession
    ):
        stmt = (
            select(Playbook)
            .where(
                and_(
                    Playbook.is_enabled == True,
                    Playbook.is_auto_executable == True,
                )
            )
        )
        result = await db.execute(stmt)
        playbooks = result.scalars().all()

        for pb in playbooks:
            if pb.applicable_anomaly_types and anomaly.anomaly_type not in pb.applicable_anomaly_types:
                continue
            if pb.applicable_systems and anomaly.system_name not in pb.applicable_systems:
                continue
            if pb.applicable_severities and anomaly.severity not in pb.applicable_severities:
                continue
            if pb.auto_execute_max_severity:
                severity_order = ["low", "medium", "high", "critical"]
                if severity_order.index(anomaly.severity.lower()) > severity_order.index(
                    pb.auto_execute_max_severity.lower()
                ):
                    continue
            return pb
        return None

    async def update_work_order_status(
        self,
        work_order_id: str,
        new_status: str,
        user_id: Optional[str] = None,
        note: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[WorkOrder]:
        valid_transitions = {
            "pending": ["assigned", "cancelled", "closed"],
            "assigned": ["in_progress", "pending", "escalated", "closed"],
            "in_progress": ["verifying", "completed", "escalated", "assigned"],
            "verifying": ["completed", "in_progress", "escalated"],
            "completed": ["closed"],
            "escalated": ["in_progress", "completed", "closed"],
            "closed": [],
        }

        async def _update(db):
            result = await db.execute(
                select(WorkOrder).where(WorkOrder.id == work_order_id)
            )
            order = result.scalar_one_or_none()
            if order is None:
                return None

            if new_status not in valid_transitions.get(order.status, []):
                raise ValueError(
                    f"Invalid status transition: {order.status} -> {new_status}"
                )

            old_status = order.status
            order.status = new_status
            now = datetime.now(timezone.utc)

            if new_status == "assigned" and order.first_response_at is None:
                order.first_response_at = now

            if new_status == "in_progress" and order.started_at is None:
                order.started_at = now

            if new_status == "verifying":
                pass

            if new_status == "completed":
                order.resolved_at = now
                if order.started_at:
                    duration = (now - order.started_at).total_seconds() / 60
                    order.actual_resolution_minutes = int(duration)

                anomaly_result = await db.execute(
                    select(Anomaly).where(Anomaly.id == order.anomaly_id)
                )
                anomaly = anomaly_result.scalar_one_or_none()
                if anomaly:
                    anomaly.status = "resolved"
                    anomaly.resolved_time = now
                    anomaly.resolution_method = "manual"
                    if note:
                        anomaly.resolution_note = note

                await db.execute(
                    select(FollowUpTask).where(
                        and_(
                            FollowUpTask.work_order_id == order.id,
                            FollowUpTask.status == "pending",
                        )
                    ).update({"status": "completed"})
                )

            if new_status == "closed":
                order.closed_at = now

            if new_status == "escalated":
                order.is_escalated = True
                order.escalation_count += 1
                await self._create_follow_up_task(order, db, "escalation")

            if note:
                if order.resolution_steps is None:
                    order.resolution_steps = []
                order.resolution_steps.append({
                    "timestamp": now.isoformat(),
                    "user_id": str(user_id) if user_id else None,
                    "from_status": old_status,
                    "to_status": new_status,
                    "note": note,
                })

            await db.commit()
            await db.refresh(order)

            logger.info(
                f"Work order {order.order_no} status changed: {old_status} -> {new_status}"
                + (f" by user {user_id}" if user_id else "")
            )

            return order

        if db is None:
            async with async_session_maker() as db:
                return await _update(db)
        else:
            return await _update(db)

    async def reassign_work_order(
        self,
        work_order_id: str,
        team_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        user_id: Optional[str] = None,
        reason: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[WorkOrder]:
        async def _reassign(db):
            result = await db.execute(
                select(WorkOrder).where(WorkOrder.id == work_order_id)
            )
            order = result.scalar_one_or_none()
            if order is None:
                return None

            old_team = order.assigned_team_id
            old_assignee = order.assignee_id

            if team_id:
                order.assigned_team_id = uuid.UUID(team_id)
            if assignee_id:
                order.assignee_id = uuid.UUID(assignee_id)
                if order.status == "pending":
                    order.status = "assigned"
                    order.first_response_at = datetime.now(timezone.utc)

            if order.resolution_steps is None:
                order.resolution_steps = []
            order.resolution_steps.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": str(user_id) if user_id else None,
                "action": "reassign",
                "old_team_id": str(old_team) if old_team else None,
                "new_team_id": team_id,
                "old_assignee_id": str(old_assignee) if old_assignee else None,
                "new_assignee_id": assignee_id,
                "reason": reason,
            })

            await db.commit()
            await db.refresh(order)

            logger.info(
                f"Work order {order.order_no} reassigned: "
                f"team {old_team} -> {team_id}, "
                f"assignee {old_assignee} -> {assignee_id}"
            )

            return order

        if db is None:
            async with async_session_maker() as db:
                return await _reassign(db)
        else:
            return await _reassign(db)

    async def process_escalations_and_reminders(self):
        logger.info("Processing work order escalations and reminders...")
        async with async_session_maker() as db:
            now = datetime.now(timezone.utc)
            escalated = 0
            reminded = 0
            new_tasks_created = 0

            result = await db.execute(
                select(WorkOrder).where(
                    and_(
                        WorkOrder.status.in_(["pending", "assigned", "in_progress", "verifying"]),
                    )
                )
            )
            orders = result.scalars().all()

            for order in orders:
                try:
                    if order.sla_deadline and now > order.sla_deadline and not order.is_escalated:
                        order.is_escalated = True
                        order.escalation_count += 1
                        order.status = "escalated"
                        await self._create_follow_up_task(order, db, "escalation")
                        escalated += 1
                        continue

                    if order.last_reminder_at:
                        time_since_reminder = (now - order.last_reminder_at).total_seconds() / 3600
                        if time_since_reminder < self._escalation_interval_hours:
                            continue

                    needs_reminder = False
                    if order.status == "pending":
                        pending_hours = (now - order.created_at).total_seconds() / 3600
                        needs_reminder = pending_hours >= 0.5
                    elif order.status == "assigned":
                        response_sla = self._sla_configs.get(order.priority, {}).get("response_minutes", 60)
                        assigned_hours = (now - (order.first_response_at or order.created_at)).total_seconds() / 3600
                        needs_reminder = assigned_hours * 60 >= response_sla * 0.5
                    elif order.status == "in_progress":
                        resolution_sla = self._sla_configs.get(order.priority, {}).get("resolution_minutes", 480)
                        progress_hours = (now - (order.started_at or order.created_at)).total_seconds() / 3600
                        needs_reminder = progress_hours * 60 >= resolution_sla * 0.75

                    if needs_reminder:
                        order.reminder_count += 1
                        order.last_reminder_at = now
                        reminded += 1

                        pending_task_result = await db.execute(
                            select(FollowUpTask).where(
                                and_(
                                    FollowUpTask.work_order_id == order.id,
                                    FollowUpTask.status == "pending",
                                )
                            )
                        )
                        if not pending_task_result.scalar_one_or_none():
                            await self._create_follow_up_task(order, db, "manual_follow_up")
                            new_tasks_created += 1

                except Exception as e:
                    logger.error(f"Error processing order {order.order_no}: {e}", exc_info=True)

            await self._process_follow_up_tasks(db)

            await db.commit()

            logger.info(
                f"Escalation processing complete: "
                f"escalated={escalated}, reminded={reminded}, new_tasks={new_tasks_created}"
            )
            return {
                "escalated": escalated,
                "reminded": reminded,
                "new_tasks_created": new_tasks_created,
            }

    async def _process_follow_up_tasks(self, db: AsyncSession):
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(FollowUpTask).where(
                and_(
                    FollowUpTask.status == "pending",
                    FollowUpTask.next_follow_up_at <= now,
                )
            )
        )
        tasks = result.scalars().all()

        for task in tasks:
            try:
                task.follow_up_count += 1
                task.last_follow_up_at = now

                if task.follow_up_count >= task.escalate_after_follow_ups and not task.is_escalation_triggered:
                    task.is_escalation_triggered = True

                    wo_result = await db.execute(
                        select(WorkOrder).where(WorkOrder.id == task.work_order_id)
                    )
                    order = wo_result.scalar_one_or_none()
                    if order:
                        order.is_escalated = True
                        order.escalation_count += 1

                task.next_follow_up_at = now + timedelta(hours=task.follow_up_interval_hours)

                if task.notes is None:
                    task.notes = []
                task.notes.append({
                    "timestamp": now.isoformat(),
                    "type": "auto_reminder",
                    "count": task.follow_up_count,
                    "escalation_triggered": task.is_escalation_triggered,
                })

            except Exception as e:
                logger.error(f"Error processing follow-up task {task.id}: {e}")

    async def process_new_anomalies(self):
        logger.info("Checking for new anomalies to create work orders...")
        async with async_session_maker() as db:
            result = await db.execute(
                select(Anomaly)
                .outerjoin(WorkOrder, WorkOrder.anomaly_id == Anomaly.id)
                .where(
                    and_(
                        WorkOrder.id.is_(None),
                        Anomaly.status.in_(["open", "investigating"]),
                    )
                )
                .order_by(Anomaly.detected_time.desc())
                .limit(100)
            )
            anomalies = result.scalars().all()

        created = 0
        for anomaly in anomalies:
            try:
                wo = await self.create_work_order_for_anomaly(str(anomaly.id))
                if wo:
                    created += 1
            except Exception as e:
                logger.error(f"Failed to create work order for anomaly {anomaly.id}: {e}")

        logger.info(f"Created {created} new work orders")
        return created


ticket_service = TicketService()
