from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, BigInteger, Index, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from ..database import Base


class Playbook(Base):
    __tablename__ = "playbooks"
    __table_args__ = (
        Index("idx_playbook_trigger", "trigger_condition_type", "is_auto_executable"),
        {"comment": "预案表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="预案ID")
    name = Column(String(200), nullable=False, unique=True, comment="预案名称")
    description = Column(Text, nullable=True, comment="预案描述")
    playbook_type = Column(String(30), nullable=False, comment="预案类型")
    applicable_anomaly_types = Column(JSON, nullable=True, comment="适用异常类型列表")
    applicable_systems = Column(JSON, nullable=True, comment="适用系统列表")
    applicable_severities = Column(JSON, nullable=True, comment="适用严重等级列表")
    trigger_condition_type = Column(String(30), nullable=False, default="manual", comment="触发条件类型")
    trigger_rule = Column(JSON, nullable=True, comment="自动触发规则")
    execution_steps = Column(JSON, nullable=False, comment="执行步骤列表")
    parameters_schema = Column(JSON, nullable=True, comment="参数Schema定义")
    target_service = Column(String(100), nullable=True, comment="目标服务")
    rollback_steps = Column(JSON, nullable=True, comment="回滚步骤")
    verification_method = Column(String(50), nullable=True, comment="验证方式")
    verification_rules = Column(JSON, nullable=True, comment="验证规则")
    verification_timeout_seconds = Column(Integer, nullable=False, default=300, comment="验证超时时间(秒)")
    is_auto_executable = Column(Boolean, default=False, comment="是否可自动执行")
    auto_execute_max_severity = Column(String(10), nullable=True, comment="自动执行最大严重等级")
    require_approval = Column(Boolean, default=True, comment="是否需要审批")
    approver_role = Column(String(20), nullable=True, comment="审批角色")
    estimated_duration_seconds = Column(Integer, nullable=True, comment="预估执行时长(秒)")
    success_rate = Column(Numeric(5, 2), nullable=True, comment="历史成功率")
    execution_count = Column(Integer, nullable=False, default=0, comment="执行次数")
    success_count = Column(Integer, nullable=False, default=0, comment="成功次数")
    is_enabled = Column(Boolean, default=True, comment="是否启用")
    created_by = Column(String(64), ForeignKey("users.id"), nullable=True, comment="创建人ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    executions = relationship("PlaybookExecution", back_populates="playbook")
    creator = relationship("User", foreign_keys=[created_by])


class PlaybookExecution(Base):
    __tablename__ = "playbook_executions"
    __table_args__ = (
        Index("idx_playbook_exec_order", "work_order_id"),
        Index("idx_playbook_exec_status", "status"),
        {"comment": "预案执行记录表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="执行ID")
    execution_no = Column(String(30), nullable=False, unique=True, comment="执行编号")
    playbook_id = Column(String(64), ForeignKey("playbooks.id"), nullable=False, index=True, comment="预案ID")
    work_order_id = Column(String(64), ForeignKey("work_orders.id"), nullable=True, index=True, comment="关联工单ID")
    anomaly_id = Column(String(64), ForeignKey("anomalies.id"), nullable=True, index=True, comment="关联异常ID")
    trigger_type = Column(String(20), nullable=False, comment="触发类型")
    status = Column(String(20), nullable=False, default="pending", comment="状态")
    executor_id = Column(String(64), ForeignKey("users.id"), nullable=True, index=True, comment="执行人ID")
    approver_id = Column(String(64), ForeignKey("users.id"), nullable=True, comment="审批人ID")
    approval_status = Column(String(20), nullable=True, comment="审批状态")
    approval_at = Column(DateTime(timezone=True), nullable=True, comment="审批时间")
    approval_note = Column(Text, nullable=True, comment="审批备注")
    execution_parameters = Column(JSON, nullable=True, comment="执行参数")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="开始时间")
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="完成时间")
    duration_seconds = Column(Integer, nullable=True, comment="实际执行时长(秒)")
    current_step_index = Column(Integer, nullable=True, comment="当前步骤索引")
    step_results = Column(JSON, nullable=True, comment="各步骤执行结果")
    execution_log = Column(Text, nullable=True, comment="执行日志")
    result_summary = Column(Text, nullable=True, comment="执行结果摘要")
    verification_started_at = Column(DateTime(timezone=True), nullable=True, comment="验证开始时间")
    verification_completed_at = Column(DateTime(timezone=True), nullable=True, comment="验证完成时间")
    verification_result = Column(String(20), nullable=True, comment="验证结果")
    verification_metrics = Column(JSON, nullable=True, comment="验证指标数据")
    verification_note = Column(Text, nullable=True, comment="验证备注")
    is_rollback_needed = Column(Boolean, default=False, comment="是否需要回滚")
    rollback_started_at = Column(DateTime(timezone=True), nullable=True, comment="回滚开始时间")
    rollback_completed_at = Column(DateTime(timezone=True), nullable=True, comment="回滚完成时间")
    rollback_result = Column(String(20), nullable=True, comment="回滚结果")
    error_code = Column(String(50), nullable=True, comment="错误码")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    playbook = relationship("Playbook", back_populates="executions")
    work_order = relationship("WorkOrder", back_populates="playbook_executions")
    executor = relationship("User", foreign_keys=[executor_id], back_populates="playbook_executions")
    approver = relationship("User", foreign_keys=[approver_id])
