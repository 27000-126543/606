from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, BigInteger, Index, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from ..database import Base


class MetricBaseline(Base):
    __tablename__ = "metric_baselines"
    __table_args__ = (
        Index("idx_baseline_metric_time", "system_name", "metric_name", "time_window", "period_start"),
        {"comment": "指标基线表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="基线ID")
    system_name = Column(String(100), nullable=False, index=True, comment="系统名称")
    metric_name = Column(String(100), nullable=False, comment="指标名称")
    metric_category = Column(String(50), nullable=True, comment="指标分类")
    time_window = Column(String(10), nullable=False, default="5m", comment="时间窗口")
    period_start = Column(DateTime(timezone=True), nullable=False, index=True, comment="基线周期开始时间")
    period_end = Column(DateTime(timezone=True), nullable=False, comment="基线周期结束时间")
    baseline_value = Column(Numeric(18, 4), nullable=False, comment="基线值")
    upper_bound = Column(Numeric(18, 4), nullable=False, comment="上界阈值")
    lower_bound = Column(Numeric(18, 4), nullable=True, comment="下界阈值")
    mean_value = Column(Numeric(18, 4), nullable=True, comment="均值")
    std_dev = Column(Numeric(18, 4), nullable=True, comment="标准差")
    variance = Column(Numeric(18, 4), nullable=True, comment="方差")
    percentile_25 = Column(Numeric(18, 4), nullable=True, comment="25分位值")
    percentile_50 = Column(Numeric(18, 4), nullable=True, comment="50分位值")
    percentile_75 = Column(Numeric(18, 4), nullable=True, comment="75分位值")
    percentile_90 = Column(Numeric(18, 4), nullable=True, comment="90分位值")
    percentile_95 = Column(Numeric(18, 4), nullable=True, comment="95分位值")
    percentile_99 = Column(Numeric(18, 4), nullable=True, comment="99分位值")
    min_value = Column(Numeric(18, 4), nullable=True, comment="最小值")
    max_value = Column(Numeric(18, 4), nullable=True, comment="最大值")
    sample_count = Column(Integer, nullable=False, default=0, comment="样本数量")
    algorithm = Column(String(30), nullable=False, default="dynamic_baseline", comment="算法类型")
    seasonality_components = Column(JSON, nullable=True, comment="季节性分量")
    trend_components = Column(JSON, nullable=True, comment="趋势分量")
    confidence_level = Column(Numeric(3, 2), nullable=False, default=0.99, comment="置信水平")
    is_stationary = Column(Boolean, nullable=True, comment="是否平稳序列")
    adf_statistic = Column(Numeric(12, 6), nullable=True, comment="ADF检验统计量")
    adf_p_value = Column(Numeric(6, 4), nullable=True, comment="ADF检验P值")
    is_valid = Column(Boolean, default=True, comment="基线是否有效")
    invalid_reason = Column(String(200), nullable=True, comment="失效原因")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")


class BaselineHistory(Base):
    __tablename__ = "baseline_history"
    __table_args__ = (
        Index("idx_baseline_hist_time", "baseline_id", "history_time"),
        {"comment": "基线历史检测记录表"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="记录ID")
    baseline_id = Column(String(64), ForeignKey("metric_baselines.id"), nullable=False, index=True, comment="基线ID")
    history_time = Column(DateTime(timezone=True), nullable=False, index=True, comment="检测时间点")
    actual_value = Column(Numeric(18, 4), nullable=False, comment="实际指标值")
    baseline_value_at_time = Column(Numeric(18, 4), nullable=True, comment="该时间点的基线值")
    upper_bound_at_time = Column(Numeric(18, 4), nullable=True, comment="该时间点的上界")
    lower_bound_at_time = Column(Numeric(18, 4), nullable=True, comment="该时间点的下界")
    deviation_from_baseline = Column(Numeric(18, 4), nullable=True, comment="偏离基线的绝对值")
    deviation_percent = Column(Numeric(10, 4), nullable=True, comment="偏离百分比(%)")
    z_score = Column(Numeric(12, 6), nullable=True, comment="Z分数")
    is_anomaly = Column(Boolean, nullable=False, default=False, comment="是否异常")
    anomaly_severity = Column(String(10), nullable=True, comment="异常严重等级")
    triggered_anomaly_id = Column(String(64), ForeignKey("anomalies.id"), nullable=True, comment="触发的异常ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="记录时间")

    baseline = relationship("MetricBaseline")
    triggered_anomaly = relationship("Anomaly")
