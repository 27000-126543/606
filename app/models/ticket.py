from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, BigInteger, Index, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from ..database import Base


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        Index("idx_work_orders_team_status", "assigned_team_id", "status"),
        Index("idx_work_orders_assignee", "assignee_id", "status"),
        Index("idx_work_orders_priority", "priority"),
        {"comment": "工单表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="工单ID")
    order_no = Column(String(30), nullable=False, unique=True, comment="工单编号")
    anomaly_id = Column(String(64), ForeignKey("anomalies.id"), nullable=False, unique=True, comment="关联异常ID")
    title = Column(String(500), nullable=False, comment="工单标题")
    description = Column(Text, nullable=True, comment="工单描述")
    anomaly_type = Column(String(50), nullable=False, comment="异常类型")
    severity = Column(String(10), nullable=False, comment="严重等级")
    priority = Column(String(10), nullable=False, default="P3", comment="优先级")
    impact_scope = Column(String(20), nullable=False, comment="影响范围")
    assigned_team_id = Column(String(64), ForeignKey("teams.id"), nullable=False, index=True, comment="指派团队ID")
    assignee_id = Column(String(64), ForeignKey("users.id"), nullable=True, index=True, comment="指派人员ID")
    creator_id = Column(String(64), ForeignKey("users.id"), nullable=True, index=True, comment="创建人ID")
    auto_assigned = Column(Boolean, default=True, comment="是否自动分配")
    status = Column(String(20), nullable=False, default="pending", comment="状态")
    sla_deadline = Column(DateTime(timezone=True), nullable=True, comment="SLA截止时间")
    first_response_at = Column(DateTime(timezone=True), nullable=True, comment="首次响应时间")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="开始处理时间")
    resolved_at = Column(DateTime(timezone=True), nullable=True, comment="解决时间")
    verified_at = Column(DateTime(timezone=True), nullable=True, comment="验证通过时间")
    closed_at = Column(DateTime(timezone=True), nullable=True, comment="关闭时间")
    actual_resolution_minutes = Column(Integer, nullable=True, comment="实际修复时长(分钟)")
    playbook_executed = Column(Boolean, default=False, comment="是否执行过预案")
    resolution_steps = Column(JSON, nullable=True, comment="处理步骤记录")
    resolution_summary = Column(Text, nullable=True, comment="处理总结")
    root_cause_category = Column(String(50), nullable=True, comment="根因分类")
    is_escalated = Column(Boolean, default=False, comment="是否已升级")
    escalation_count = Column(Integer, nullable=False, default=0, comment="升级次数")
    last_reminder_at = Column(DateTime(timezone=True), nullable=True, comment="最后催办时间")
    reminder_count = Column(Integer, nullable=False, default=0, comment="催办次数")
    tags = Column(JSON, nullable=True, comment="标签")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    anomaly = relationship("Anomaly", back_populates="work_order")
    assigned_team = relationship("Team", back_populates="work_orders")
    assignee = relationship("User", foreign_keys=[assignee_id], back_populates="assigned_work_orders")
    creator = relationship("User", foreign_keys=[creator_id], back_populates="created_work_orders")
    follow_up_tasks = relationship("FollowUpTask", back_populates="work_order", cascade="all, delete-orphan")
    playbook_executions = relationship("PlaybookExecution", back_populates="work_order")


class FollowUpTask(Base):
    __tablename__ = "follow_up_tasks"
    __table_args__ = (
        Index("idx_followup_status", "status"),
        Index("idx_followup_deadline", "next_follow_up_at"),
        {"comment": "跟进任务表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="任务ID")
    work_order_id = Column(String(64), ForeignKey("work_orders.id"), nullable=False, index=True, comment="关联工单ID")
    task_type = Column(String(30), nullable=False, default="manual_follow_up", comment="任务类型")
    title = Column(String(500), nullable=False, comment="任务标题")
    description = Column(Text, nullable=True, comment="任务描述")
    assigned_to_id = Column(String(64), ForeignKey("users.id"), nullable=True, comment="指派给")
    status = Column(String(20), nullable=False, default="pending", comment="状态")
    priority = Column(String(10), nullable=False, default="P2", comment="优先级")
    next_follow_up_at = Column(DateTime(timezone=True), nullable=True, index=True, comment="下次跟进时间")
    follow_up_interval_hours = Column(Integer, nullable=False, default=4, comment="跟进间隔(小时)")
    follow_up_count = Column(Integer, nullable=False, default=0, comment="已跟进次数")
    last_follow_up_at = Column(DateTime(timezone=True), nullable=True, comment="上次跟进时间")
    last_follow_up_note = Column(Text, nullable=True, comment="上次跟进备注")
    escalate_after_follow_ups = Column(Integer, nullable=False, default=3, comment="多少次跟进后升级")
    is_escalation_triggered = Column(Boolean, default=False, comment="是否已触发升级")
    notes = Column(JSON, nullable=True, comment="跟进记录列表")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    work_order = relationship("WorkOrder", back_populates="follow_up_tasks")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
