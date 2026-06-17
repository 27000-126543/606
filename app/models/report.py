from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, BigInteger, Index, Table, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from ..database import Base


anomaly_case_matches = Table(
    "anomaly_case_matches",
    Base.metadata,
    Column("anomaly_id", String(64), ForeignKey("anomalies.id"), primary_key=True),
    Column("case_id", String(64), ForeignKey("case_library.id"), primary_key=True),
    Column("match_score", Numeric(5, 4), nullable=False, comment="匹配度(0-1)"),
    Column("matched_at", DateTime(timezone=True), server_default=func.now(), comment="匹配时间"),
    comment="异常-案例匹配关联表"
)


class CaseLibrary(Base):
    __tablename__ = "case_library"
    __table_args__ = (
        Index("idx_case_system", "system_name"),
        Index("idx_case_category", "category"),
        {"comment": "案例库表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="案例ID")
    case_no = Column(String(30), nullable=False, unique=True, comment="案例编号")
    title = Column(String(500), nullable=False, comment="案例标题")
    system_name = Column(String(100), nullable=True, index=True, comment="适用系统")
    anomaly_type = Column(String(50), nullable=True, comment="异常类型")
    severity = Column(String(10), nullable=True, comment="严重等级")
    category = Column(String(50), nullable=True, index=True, comment="分类")
    tags = Column(JSON, nullable=True, comment="标签")
    keywords = Column(JSON, nullable=True, comment="关键词(用于匹配)")
    symptom_description = Column(Text, nullable=False, comment="现象描述")
    root_cause = Column(Text, nullable=False, comment="根本原因")
    root_cause_category = Column(String(50), nullable=True, comment="根因分类")
    resolution_steps = Column(JSON, nullable=False, comment="解决步骤列表")
    recommended_playbook_ids = Column(JSON, nullable=True, comment="推荐预案ID列表")
    affected_services = Column(JSON, nullable=True, comment="影响服务")
    prevention_measures = Column(Text, nullable=True, comment="预防措施")
    reference_links = Column(JSON, nullable=True, comment="参考链接列表")
    occurrence_count = Column(Integer, nullable=False, default=0, comment="历史发生次数")
    resolution_time_avg_minutes = Column(Integer, nullable=True, comment="平均解决时长(分钟)")
    success_rate = Column(Numeric(5, 2), nullable=True, comment="解决方案成功率")
    is_verified = Column(Boolean, default=False, comment="是否经验证")
    verified_by = Column(String(64), ForeignKey("users.id"), nullable=True, comment="验证人ID")
    verified_at = Column(DateTime(timezone=True), nullable=True, comment="验证时间")
    feature_vector = Column(JSON, nullable=True, comment="特征向量(用于相似度匹配)")
    imported_from = Column(String(50), nullable=True, comment="导入来源")
    source_anomaly_id = Column(String(64), ForeignKey("anomalies.id"), nullable=True, comment="来源异常ID")
    created_by = Column(String(64), ForeignKey("users.id"), nullable=True, comment="创建人ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    matched_anomalies = relationship("Anomaly", secondary=anomaly_case_matches, back_populates="case_matches")
    created_by_user = relationship("User", foreign_keys=[created_by])
    verified_by_user = relationship("User", foreign_keys=[verified_by])
    source_anomaly = relationship("Anomaly", foreign_keys=[source_anomaly_id])


class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        Index("idx_daily_report_date", "report_date"),
        {"comment": "每日汇总报表"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="报表ID")
    report_date = Column(DateTime(timezone=True), nullable=False, unique=True, index=True, comment="报表日期")
    total_anomalies = Column(Integer, nullable=False, default=0, comment="总异常数")
    critical_anomalies = Column(Integer, nullable=False, default=0, comment="严重异常数")
    high_anomalies = Column(Integer, nullable=False, default=0, comment="高危异常数")
    medium_anomalies = Column(Integer, nullable=False, default=0, comment="中等异常数")
    low_anomalies = Column(Integer, nullable=False, default=0, comment="低危异常数")
    new_anomalies = Column(Integer, nullable=False, default=0, comment="新增异常数")
    resolved_anomalies = Column(Integer, nullable=False, default=0, comment="已解决异常数")
    unresolved_anomalies = Column(Integer, nullable=False, default=0, comment="未解决异常数")
    auto_resolved = Column(Integer, nullable=False, default=0, comment="自动解决数")
    manual_resolved = Column(Integer, nullable=False, default=0, comment="手动解决数")
    playbook_resolved = Column(Integer, nullable=False, default=0, comment="预案解决数")
    escalated_count = Column(Integer, nullable=False, default=0, comment="升级次数")
    total_work_orders = Column(Integer, nullable=False, default=0, comment="总工单数")
    completed_work_orders = Column(Integer, nullable=False, default=0, comment="已完成工单数")
    avg_resolution_minutes = Column(Numeric(12, 2), nullable=True, comment="平均修复时长(分钟)")
    median_resolution_minutes = Column(Numeric(12, 2), nullable=True, comment="中位数修复时长")
    p95_resolution_minutes = Column(Numeric(12, 2), nullable=True, comment="P95修复时长")
    repeat_rate = Column(Numeric(5, 2), nullable=True, comment="重复率(%)")
    top_anomaly_types = Column(JSON, nullable=True, comment="Top异常类型统计")
    top_affected_systems = Column(JSON, nullable=True, comment="Top受影响系统")
    top_root_causes = Column(JSON, nullable=True, comment="Top根因分类")
    sla_breach_count = Column(Integer, nullable=False, default=0, comment="SLA违规次数")
    sla_compliance_rate = Column(Numeric(5, 2), nullable=True, comment="SLA达标率(%)")
    impact_scope_breakdown = Column(JSON, nullable=True, comment="影响范围分布")
    trend_data = Column(JSON, nullable=True, comment="趋势数据(用于图表)")
    anomaly_hourly_distribution = Column(JSON, nullable=True, comment="异常小时分布")
    system_summary = Column(JSON, nullable=True, comment="按系统汇总")
    team_summary = Column(JSON, nullable=True, comment="按团队汇总")
    playbook_execution_summary = Column(JSON, nullable=True, comment="预案执行汇总")
    notable_events = Column(JSON, nullable=True, comment="重要事件列表")
    recommendations = Column(JSON, nullable=True, comment="建议列表")
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), comment="生成时间")
    generated_by = Column(String(50), nullable=True, comment="生成方式")
    pdf_file_path = Column(String(500), nullable=True, comment="PDF文件路径")
    excel_file_path = Column(String(500), nullable=True, comment="Excel文件路径")
