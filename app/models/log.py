from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, BigInteger, Index, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base

try:
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    has_pg_uuid = True
except ImportError:
    has_pg_uuid = False


class RawLog(Base):
    __tablename__ = "raw_logs"
    __table_args__ = (
        Index("idx_raw_logs_system_time", "system_name", "log_time"),
        Index("idx_raw_logs_level", "log_level"),
        {"comment": "原始日志表"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="日志ID")
    log_id = Column(String(64), nullable=False, unique=True, comment="日志唯一标识")
    system_name = Column(String(100), nullable=False, index=True, comment="来源系统名称")
    host_ip = Column(String(45), nullable=True, comment="主机IP")
    log_time = Column(DateTime(timezone=True), nullable=False, index=True, comment="日志产生时间")
    receive_time = Column(DateTime(timezone=True), server_default=func.now(), comment="接收时间")
    log_level = Column(String(10), nullable=False, default="INFO", comment="日志级别")
    module = Column(String(100), nullable=True, comment="模块名称")
    trace_id = Column(String(64), nullable=True, index=True, comment="调用链追踪ID")
    message = Column(Text, nullable=False, comment="日志消息内容")
    tags = Column(JSON, nullable=True, comment="自定义标签KV")
    extra_data = Column(JSON, nullable=True, comment="扩展数据")
    is_processed = Column(Boolean, default=False, index=True, comment="是否已处理")
    partition_key = Column(String(20), nullable=True, comment="分区键")

    anomalies = relationship("Anomaly", back_populates="triggering_log")


class ProcessedLog(Base):
    __tablename__ = "processed_logs"
    __table_args__ = (
        Index("idx_proc_logs_system_time", "system_name", "log_time"),
        Index("idx_proc_logs_metric", "system_name", "metric_name", "log_time"),
        {"comment": "处理后日志聚合表"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    system_name = Column(String(100), nullable=False, index=True, comment="系统名称")
    metric_name = Column(String(100), nullable=False, comment="指标名称")
    log_time = Column(DateTime(timezone=True), nullable=False, index=True, comment="时间窗口起始时间")
    time_window = Column(String(10), nullable=False, default="5m", comment="时间窗口: 1m/5m/15m/1h")
    metric_value = Column(Numeric(18, 4), nullable=False, comment="指标数值")
    count = Column(Integer, nullable=False, default=0, comment="日志条数")
    error_count = Column(Integer, nullable=False, default=0, comment="错误条数")
    warn_count = Column(Integer, nullable=False, default=0, comment="警告条数")
    p50 = Column(Numeric(18, 4), nullable=True, comment="P50分位值")
    p95 = Column(Numeric(18, 4), nullable=True, comment="P95分位值")
    p99 = Column(Numeric(18, 4), nullable=True, comment="P99分位值")
    avg_value = Column(Numeric(18, 4), nullable=True, comment="平均值")
    max_value = Column(Numeric(18, 4), nullable=True, comment="最大值")
    min_value = Column(Numeric(18, 4), nullable=True, comment="最小值")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
