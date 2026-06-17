from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class AnomalyResponse(BaseModel):
    id: UUID
    anomaly_code: str
    system_name: str
    anomaly_type: str
    severity: str
    title: str
    description: Optional[str]
    detected_time: datetime
    first_occurrence_time: Optional[datetime]
    last_occurrence_time: Optional[datetime]
    occurrence_count: int
    affected_services: Optional[List[str]]
    impact_scope: str
    impact_score: Optional[Decimal]
    status: str
    root_cause_analysis: Optional[Dict[str, Any]]
    is_auto_detected: bool
    detection_algorithm: Optional[str]
    confidence: Optional[Decimal]
    resolved_time: Optional[datetime]
    resolution_method: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AnomalyQueryParams(BaseModel):
    system_name: Optional[str] = None
    anomaly_type: Optional[str] = None
    severity: Optional[List[str]] = None
    status: Optional[List[str]] = None
    impact_scope: Optional[str] = None
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    keyword: Optional[str] = None
    sort_by: str = "detected_time"
    sort_order: str = "desc"
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class AnomalyListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: List[AnomalyResponse]
    total: int
    stats: Dict[str, Any]


class RootCauseAnalysisResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Dict[str, Any]


class WorkOrderResponse(BaseModel):
    id: UUID
    order_no: str
    anomaly_id: UUID
    title: str
    description: Optional[str]
    anomaly_type: str
    severity: str
    priority: str
    impact_scope: str
    assigned_team_id: Optional[UUID]
    assignee_id: Optional[UUID]
    status: str
    sla_deadline: Optional[datetime]
    first_response_at: Optional[datetime]
    started_at: Optional[datetime]
    resolved_at: Optional[datetime]
    closed_at: Optional[datetime]
    actual_resolution_minutes: Optional[int]
    playbook_executed: bool
    is_escalated: bool
    escalation_count: int
    reminder_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class WorkOrderQueryParams(BaseModel):
    assigned_team_id: Optional[str] = None
    assignee_id: Optional[str] = None
    anomaly_id: Optional[str] = None
    priority: Optional[List[str]] = None
    severity: Optional[List[str]] = None
    status: Optional[List[str]] = None
    is_escalated: Optional[bool] = None
    sla_breach: Optional[bool] = None
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    keyword: Optional[str] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class WorkOrderListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: List[WorkOrderResponse]
    total: int
    stats: Dict[str, Any]


class WorkOrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending|assigned|in_progress|verifying|completed|escalated|closed)$")
    note: Optional[str] = None


class WorkOrderReassign(BaseModel):
    team_id: Optional[str] = None
    assignee_id: Optional[str] = None
    reason: Optional[str] = None


class PlaybookResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    playbook_type: str
    applicable_anomaly_types: Optional[List[str]]
    applicable_systems: Optional[List[str]]
    trigger_condition_type: str
    execution_steps: List[Dict[str, Any]]
    verification_method: Optional[str]
    is_auto_executable: bool
    require_approval: bool
    estimated_duration_seconds: Optional[int]
    success_rate: Optional[Decimal]
    execution_count: int
    success_count: int
    is_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PlaybookExecuteRequest(BaseModel):
    playbook_id: str
    work_order_id: Optional[str] = None
    anomaly_id: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class PlaybookExecutionResponse(BaseModel):
    id: str
    execution_no: str
    playbook_id: str
    work_order_id: Optional[str] = None
    anomaly_id: Optional[str] = None
    trigger_type: str
    status: str
    approval_status: Optional[str] = None
    executor_id: Optional[str] = None
    approver_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    current_step_index: Optional[int] = None
    step_results: Optional[List[Dict[str, Any]]] = None
    result_summary: Optional[str] = None
    verification_result: Optional[str] = None
    verification_metrics: Optional[Dict[str, Any]] = None
    verification_note: Optional[str] = None
    is_rollback_needed: Optional[bool] = None
    rollback_result: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PlaybookApprovalRequest(BaseModel):
    approved: bool
    note: Optional[str] = None


class ReportResponse(BaseModel):
    id: UUID
    report_date: datetime
    total_anomalies: int
    critical_anomalies: int
    high_anomalies: int
    total_work_orders: int
    completed_work_orders: int
    avg_resolution_minutes: Optional[Decimal]
    repeat_rate: Optional[Decimal]
    sla_compliance_rate: Optional[Decimal]
    pdf_file_path: Optional[str]
    excel_file_path: Optional[str]
    generated_at: datetime

    class Config:
        from_attributes = True


class CaseMatchRequest(BaseModel):
    anomaly_id: Optional[str] = None
    event_data: Optional[Dict[str, Any]] = None
    top_k: int = Field(5, ge=1, le=20)
    min_score: float = Field(0.5, ge=0.0, le=1.0)


class CaseMatchResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: List[Dict[str, Any]]


class CaseImportRequest(BaseModel):
    title: str
    system_name: Optional[str] = None
    anomaly_type: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    symptom_description: str
    root_cause: str
    root_cause_category: Optional[str] = None
    resolution_steps: List[Dict[str, Any]]
    prevention_measures: Optional[str] = None
    affected_services: Optional[List[str]] = None
    reference_links: Optional[List[Dict[str, Any]]] = None
    success_rate: Optional[float] = 100.0


class AuditLogResponse(BaseModel):
    id: int
    audit_id: UUID
    username: Optional[str]
    module: str
    action_type: str
    action_desc: str
    target_type: Optional[str]
    target_id: Optional[str]
    target_name: Optional[str]
    status: str
    system_name: Optional[str]
    anomaly_id: Optional[UUID]
    work_order_id: Optional[UUID]
    severity_level: str
    action_time: datetime
    execution_duration_ms: Optional[int]

    class Config:
        from_attributes = True


class AuditQueryParams(BaseModel):
    user_id: Optional[str] = None
    module: Optional[str] = None
    action_type: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    system_name: Optional[str] = None
    anomaly_id: Optional[str] = None
    work_order_id: Optional[str] = None
    severity_level: Optional[str] = None
    status: Optional[str] = None
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    keyword: Optional[str] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class AuditListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: List[AuditLogResponse]
    total: int


class LogQueryParams(BaseModel):
    system_name: Optional[str] = None
    log_level: Optional[List[str]] = None
    module: Optional[str] = None
    trace_id: Optional[str] = None
    host_ip: Optional[str] = None
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    keyword: Optional[str] = None
    sort_by: str = "log_time"
    sort_order: str = "desc"
    page: int = Field(1, ge=1)
    page_size: int = Field(100, ge=1, le=5000)


class LogResponse(BaseModel):
    id: int
    log_id: UUID
    system_name: str
    host_ip: Optional[str]
    log_time: datetime
    receive_time: datetime
    log_level: str
    module: Optional[str]
    trace_id: Optional[str]
    message: str
    tags: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


class LogListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: List[LogResponse]
    total: int
    stats: Dict[str, Any]


class ExportRequest(BaseModel):
    data_type: str = Field(..., pattern="^(anomalies|work_orders|logs|audit)$")
    format: str = Field("csv", pattern="^(csv|json|excel)$")
    filters: Optional[Dict[str, Any]] = None


class ExportResponse(BaseModel):
    code: int = 200
    message: str = "导出成功"
    data: Dict[str, Any]


class SystemStatsResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Dict[str, Any]
