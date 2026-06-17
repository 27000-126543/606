from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, BigInteger, Index, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from ..database import Base


class Anomaly(Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        Index("idx_anomalies_system_time", "system_name", "detected_time"),
        Index("idx_anomalies_severity", "severity"),
        Index("idx_anomalies_status", "status"),
        {"comment": "异常记录表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="异常ID")
    anomaly_code = Column(String(50), nullable=False, unique=True, comment="异常编号")
    system_name = Column(String(100), nullable=False, index=True, comment="关联系统名称")
    triggering_log_id = Column(Integer, ForeignKey("raw_logs.id"), nullable=True, comment="触发日志ID")
    anomaly_type = Column(String(50), nullable=False, index=True, comment="异常类型")
    severity = Column(String(10), nullable=False, default="medium", comment="严重等级")
    title = Column(String(500), nullable=False, comment="异常标题")
    description = Column(Text, nullable=True, comment="异常详细描述")
    detected_time = Column(DateTime(timezone=True), nullable=False, index=True, comment="检测时间")
    first_occurrence_time = Column(DateTime(timezone=True), nullable=True, comment="首次发生时间")
    last_occurrence_time = Column(DateTime(timezone=True), nullable=True, comment="最后发生时间")
    occurrence_count = Column(Integer, nullable=False, default=1, comment="发生次数")
    affected_services = Column(JSON, nullable=True, comment="影响服务列表")
    impact_scope = Column(String(20), nullable=False, default="single", comment="影响范围")
    impact_score = Column(Numeric(5, 2), nullable=True, comment="影响评分")
    status = Column(String(20), nullable=False, default="open", comment="状态")
    root_cause_analysis = Column(JSON, nullable=True, comment="根因分析结果")
    related_change_ids = Column(JSON, nullable=True, comment="关联变更记录ID列表")
    related_dependencies = Column(JSON, nullable=True, comment="关联拓扑依赖分析")
    baseline_snapshot = Column(JSON, nullable=True, comment="检测时的基线快照")
    metric_values = Column(JSON, nullable=True, comment="异常指标值")
    is_auto_detected = Column(Boolean, default=True, comment="是否自动检测")
    detection_algorithm = Column(String(50), nullable=True, comment="检测算法")
    confidence = Column(Numeric(5, 2), nullable=True, comment="置信度")
    resolved_time = Column(DateTime(timezone=True), nullable=True, comment="解决时间")
    resolution_method = Column(String(50), nullable=True, comment="解决方式")
    resolution_note = Column(Text, nullable=True, comment="解决备注")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    triggering_log = relationship("RawLog", back_populates="anomalies")
    work_order = relationship("WorkOrder", back_populates="anomaly", uselist=False)
    case_matches = relationship("CaseLibrary", secondary="anomaly_case_matches", back_populates="matched_anomalies")


class BaselineConfig(Base):
    __tablename__ = "baseline_configs"
    __table_args__ = {"comment": "基线配置表"}

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="配置ID")
    system_name = Column(String(100), nullable=False, index=True, comment="系统名称")
    metric_name = Column(String(100), nullable=False, comment="指标名称")
    algorithm = Column(String(30), nullable=False, default="dynamic_baseline", comment="算法类型")
    sensitivity = Column(Numeric(3, 2), nullable=False, default=0.95, comment="灵敏度")
    seasonality_daily = Column(Boolean, default=True, comment="是否启用日周期性")
    seasonality_weekly = Column(Boolean, default=True, comment="是否启用周周期性")
    training_window_days = Column(Integer, nullable=False, default=14, comment="训练窗口天数")
    upper_threshold_multiplier = Column(Numeric(4, 2), nullable=False, default=3.0, comment="上界阈值倍数")
    lower_threshold_multiplier = Column(Numeric(4, 2), nullable=False, default=3.0, comment="下界阈值倍数")
    min_samples = Column(Integer, nullable=False, default=100, comment="最小样本数")
    is_enabled = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
