from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, BigInteger, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from ..database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_user_time", "user_id", "action_time"),
        Index("idx_audit_action", "action_type", "module"),
        Index("idx_audit_target", "target_type", "target_id"),
        {"comment": "审计日志表"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="审计日志ID")
    audit_id = Column(String(64), default=lambda: str(uuid.uuid4()), comment="审计唯一标识")
    user_id = Column(String(64), ForeignKey("users.id"), nullable=True, index=True, comment="操作用户ID")
    username = Column(String(50), nullable=True, comment="操作用户名")
    user_ip = Column(String(45), nullable=True, comment="用户IP地址")
    user_agent = Column(String(500), nullable=True, comment="用户Agent")
    session_id = Column(String(64), nullable=True, comment="会话ID")
    module = Column(String(50), nullable=False, index=True, comment="模块名称")
    action_type = Column(String(30), nullable=False, index=True, comment="操作类型")
    action_desc = Column(String(500), nullable=False, comment="操作描述")
    target_type = Column(String(30), nullable=True, index=True, comment="目标对象类型")
    target_id = Column(String(100), nullable=True, index=True, comment="目标对象ID")
    target_name = Column(String(200), nullable=True, comment="目标对象名称")
    before_value = Column(JSON, nullable=True, comment="操作前数据快照")
    after_value = Column(JSON, nullable=True, comment="操作后数据快照")
    changed_fields = Column(JSON, nullable=True, comment="变更字段列表")
    request_data = Column(JSON, nullable=True, comment="请求参数")
    response_data = Column(JSON, nullable=True, comment="响应数据")
    status = Column(String(20), nullable=False, default="success", comment="操作状态")
    error_message = Column(Text, nullable=True, comment="错误信息")
    system_name = Column(String(100), nullable=True, comment="关联系统名称")
    anomaly_id = Column(String(64), nullable=True, comment="关联异常ID")
    work_order_id = Column(String(64), nullable=True, comment="关联工单ID")
    severity_level = Column(String(10), nullable=True, comment="审计严重等级")
    action_time = Column(DateTime(timezone=True), server_default=func.now(), index=True, comment="操作时间")
    execution_duration_ms = Column(Integer, nullable=True, comment="执行耗时(毫秒)")
    trace_id = Column(String(64), nullable=True, comment="调用链追踪ID")
    extra_metadata = Column(JSON, nullable=True, comment="扩展元数据")

    user = relationship("User", foreign_keys=[user_id], back_populates="created_audits")
