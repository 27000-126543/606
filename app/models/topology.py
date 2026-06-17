from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, BigInteger, Index, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from ..database import Base


class ServiceNode(Base):
    __tablename__ = "service_nodes"
    __table_args__ = (
        Index("idx_service_node_system", "system_name", "is_active"),
        {"comment": "服务拓扑节点表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="节点ID")
    service_name = Column(String(100), nullable=False, comment="服务名称")
    system_name = Column(String(100), nullable=False, index=True, comment="所属系统名称")
    node_type = Column(String(30), nullable=False, comment="节点类型")
    description = Column(Text, nullable=True, comment="描述")
    host_addresses = Column(JSON, nullable=True, comment="主机地址列表")
    instance_count = Column(Integer, nullable=False, default=1, comment="实例数量")
    health_check_url = Column(String(500), nullable=True, comment="健康检查URL")
    metrics_endpoint = Column(String(500), nullable=True, comment="指标采集端点")
    owner_team_id = Column(String(64), ForeignKey("teams.id"), nullable=True, comment="负责团队ID")
    tier = Column(Integer, nullable=True, comment="服务层级")
    sla_availability = Column(Numeric(5, 4), nullable=True, comment="SLA可用性目标")
    tags = Column(JSON, nullable=True, comment="标签")
    node_metadata = Column(JSON, nullable=True, comment="元数据")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    incoming_dependencies = relationship(
        "ServiceDependency",
        foreign_keys="ServiceDependency.target_service_id",
        back_populates="target_service"
    )
    outgoing_dependencies = relationship(
        "ServiceDependency",
        foreign_keys="ServiceDependency.source_service_id",
        back_populates="source_service"
    )
    owner_team = relationship("Team")


class ServiceDependency(Base):
    __tablename__ = "service_dependencies"
    __table_args__ = (
        Index("idx_dep_source", "source_service_id"),
        Index("idx_dep_target", "target_service_id"),
        {"comment": "服务依赖关系表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="ID")
    source_service_id = Column(String(64), ForeignKey("service_nodes.id"), nullable=False, index=True, comment="源服务ID")
    target_service_id = Column(String(64), ForeignKey("service_nodes.id"), nullable=False, index=True, comment="目标服务ID")
    dependency_type = Column(String(30), nullable=False, comment="依赖类型")
    connection_method = Column(String(100), nullable=True, comment="连接方式")
    criticality = Column(String(10), nullable=False, default="medium", comment="依赖重要程度")
    avg_latency_ms = Column(Integer, nullable=True, comment="平均延迟(ms)")
    failure_impact = Column(String(20), nullable=True, comment="故障影响")
    fallback_available = Column(Boolean, default=False, comment="是否有降级方案")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    source_service = relationship("ServiceNode", foreign_keys=[source_service_id], back_populates="outgoing_dependencies")
    target_service = relationship("ServiceNode", foreign_keys=[target_service_id], back_populates="incoming_dependencies")


class ChangeRecord(Base):
    __tablename__ = "change_records"
    __table_args__ = (
        Index("idx_change_time", "change_time"),
        Index("idx_change_system", "affected_system", "change_time"),
        {"comment": "变更记录表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="变更ID")
    change_no = Column(String(50), nullable=False, unique=True, comment="变更编号")
    change_type = Column(String(30), nullable=False, comment="变更类型")
    change_subtype = Column(String(50), nullable=True, comment="变更子类型")
    title = Column(String(500), nullable=False, comment="变更标题")
    description = Column(Text, nullable=True, comment="变更描述")
    affected_system = Column(String(100), nullable=False, index=True, comment="影响系统")
    affected_services = Column(JSON, nullable=True, comment="影响服务列表")
    affected_instances = Column(JSON, nullable=True, comment="影响实例列表")
    change_time = Column(DateTime(timezone=True), nullable=False, index=True, comment="变更执行时间")
    expected_end_time = Column(DateTime(timezone=True), nullable=True, comment="预计完成时间")
    actual_end_time = Column(DateTime(timezone=True), nullable=True, comment="实际完成时间")
    initiator = Column(String(100), nullable=True, comment="发起人")
    implementer = Column(String(100), nullable=True, comment="执行人")
    approver = Column(String(100), nullable=True, comment="审批人")
    status = Column(String(20), nullable=False, default="completed", comment="状态")
    risk_level = Column(String(10), nullable=True, comment="风险等级")
    config_before = Column(JSON, nullable=True, comment="变更前配置快照")
    config_after = Column(JSON, nullable=True, comment="变更后配置快照")
    rollback_plan = Column(Text, nullable=True, comment="回滚方案")
    change_source = Column(String(30), nullable=True, comment="来源")
    external_id = Column(String(100), nullable=True, comment="外部系统关联ID")
    result_note = Column(Text, nullable=True, comment="结果备注")
    tags = Column(JSON, nullable=True, comment="标签")
    is_rollback = Column(Boolean, default=False, comment="是否是回滚操作")
    rollback_of_change_id = Column(String(64), ForeignKey("change_records.id"), nullable=True, comment="回滚的原变更ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    rollback_of = relationship("ChangeRecord", remote_side=[id], backref="rollbacks")
