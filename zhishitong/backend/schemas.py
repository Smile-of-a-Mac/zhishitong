"""Pydantic 请求/响应模型"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ===== 认证 =====

class LoginRequest(BaseModel):
    """登录请求：不限制密码长度（历史用户可能使用短密码）"""
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserCreate(BaseModel):
    """注册请求：强制密码至少 8 位"""
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    tier: str
    llm_ocr_quota: int
    llm_ocr_used: int
    is_active: bool
    is_admin: bool
    is_school_admin: bool = False
    is_dept_admin: bool = False
    is_finance_admin: bool = False
    department: Optional[str] = None
    school: Optional[str] = None
    # 个人信息
    real_name: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    student_id: Optional[str] = None
    major: Optional[str] = None
    class_name: Optional[str] = None
    enrollment_year: Optional[int] = None
    advisor: Optional[str] = None
    employee_id: Optional[str] = None
    title: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ===== 审批阶段 =====

class ApprovalStageInfo(BaseModel):
    stage: str                         # dept_review / finance_review / school_review
    label: str                         # 阶段中文名
    status: str                        # pending / approved / rejected / skipped
    reviewer: Optional[str] = None     # 审批人用户名
    reason: Optional[str] = None       # 审批意见
    reviewed_at: Optional[str] = None  # 审批时间


# ===== 管理员 — API Key 管理 =====

class ApiKeyCreate(BaseModel):
    key_type: str = Field(..., pattern=r"^(ocr|json_fill)$")
    provider: str = Field(..., min_length=1, max_length=64)
    api_base: str = Field(..., min_length=1, max_length=256)
    api_key_plain: str = Field(..., min_length=1, max_length=512)
    default_model: str = Field(..., min_length=1, max_length=128)
    note: str = ""


class ApiKeyOut(BaseModel):
    id: int
    key_type: str
    provider: str
    api_base: str
    default_model: str
    is_active: bool
    fail_count: int
    last_used_at: Optional[datetime]
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ===== OCR =====

class OCRResult(BaseModel):
    text: str
    provider: str           # local_easyocr | llm_multimodal
    tier: str
    quota_remaining: Optional[int] = None
    document_type: Optional[str] = None
    filled_json: Optional[dict] = None
    record_id: Optional[int] = None


# ===== 审批 =====

class ApprovalSubmit(BaseModel):
    record_id: int
    edited_json: Optional[dict] = None


class ApprovalOut(BaseModel):
    id: int
    document_type: Optional[str]
    status: str
    current_stage: Optional[str] = None
    decision_reason: Optional[str]
    filled_json: Optional[str]
    suggestions: Optional[str] = None
    missing_info: Optional[str] = None
    original_filename: Optional[str] = None
    image_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalListOut(BaseModel):
    items: list[ApprovalOut]
    total: int
    page: int
    page_size: int


# ===== 管理 — 数据查询 =====

class DataQuery(BaseModel):
    username: Optional[str] = None
    status: Optional[str] = None
    document_type: Optional[str] = None
    page: int = 1
    page_size: int = 20


class DataItemOut(BaseModel):
    id: int
    username: str
    original_filename: Optional[str]
    document_type: Optional[str]
    status: str
    is_deleted: bool
    deleted_by: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DataListOut(BaseModel):
    items: list[DataItemOut]
    total: int
    page: int
    page_size: int


# ===== 模板 =====

class TemplateField(BaseModel):
    key: str
    label: str
    type: str
    required: bool = False
    options: Optional[list[str]] = None
    hint: Optional[str] = None


class TemplateOut(BaseModel):
    key: str
    label: str
    icon: str
    fields: list[TemplateField]


# ===== 审计日志 =====

class AuditLogOut(BaseModel):
    id: int
    admin_id: int
    action: str
    target_type: str
    target_id: Optional[int]
    detail: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ===== 系统监控 =====

class ServiceStatus(BaseModel):
    name: str
    status: str            # ok / degraded / down
    detail: str = ""
    checked_at: str = ""


class SystemHealth(BaseModel):
    overall: str           # healthy / degraded / critical
    services: list[ServiceStatus]
    uptime_seconds: float
    db_status: str
    disk_usage_percent: Optional[float] = None


class SystemStats(BaseModel):
    total_users: int
    active_users_today: int
    ocr_calls_today: int
    ocr_calls_by_tier: dict     # {"free": N, "pro": N, "pro_plus": N}
    approvals_today: int
    approvals_by_status: dict   # {"pending": N, "approved": N, "rejected": N, ...}
    errors_24h: int
    inference_uptime_percent: float = 100.0


class SystemLogOut(BaseModel):
    id: Optional[int] = None
    timestamp: str
    category: str
    level: str
    message: str
    user_id: Optional[int] = None
    record_id: Optional[int] = None
    duration_ms: Optional[int] = None
    error_trace: Optional[str] = None
    extra: dict = {}


class LogQuery(BaseModel):
    category: Optional[str] = None
    level: Optional[str] = None
    limit: int = 100


class ErrorSummary(BaseModel):
    category: str
    message: str
    count: int


# ===== 部门管理员 =====

class ApprovalStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(approved|rejected|needs_revision)$")  # 部门管理员手动决定
    reason: str = Field(default="", max_length=256)                             # 审批意见（通过时可选，驳回/需修改时必填）


# ===== 审批意见智能建议 =====

class ReviewSuggestRequest(BaseModel):
    record_id: int
    action: str = Field(..., pattern=r"^(approved|rejected|needs_revision)$")
    admin_reason: str = ""


# ===== 手动申报 =====

class ManualSubmit(BaseModel):
    document_type: str = Field(..., pattern=r"^(reimbursement|leave|club_application|classroom_booking|business_trip|seal_application|dorm_change|scholarship|suspend_resume|enrollment_proof|abroad_application|onboarding|office_supplies|book_purchase)$")
    fields: dict  # 用户填写的字段 key-value


class DeptRecordOut(BaseModel):
    id: int
    username: str
    department: Optional[str] = None
    original_filename: Optional[str] = None
    document_type: Optional[str] = None
    status: str
    current_stage: str = "dept_review"
    filled_json: Optional[str] = None
    decision_reason: Optional[str] = None
    suggestions: Optional[str] = None
    missing_info: Optional[str] = None
    stages: list[ApprovalStageInfo] = []
    image_url: Optional[str] = None
    is_deleted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DeptRecordListOut(BaseModel):
    items: list[DeptRecordOut]
    total: int
    page: int
    page_size: int


class DeptStatsOut(BaseModel):
    department: str
    total_records: int
    pending: int
    approved: int
    rejected: int
    today_new: int


# ===== 通知 =====

class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    record_id: Optional[int] = None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int


# ===== 审批意见模板 =====

class OpinionTemplateCreate(BaseModel):
    category: str = "general"
    content: str = Field(..., min_length=1, max_length=256)
    sort_order: int = 0


class OpinionTemplateOut(BaseModel):
    id: int
    category: str
    content: str
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ===== 审批代理 =====

class DelegationCreate(BaseModel):
    delegate_id: int
    start_date: str
    end_date: str
    reason: str = ""


class DelegationOut(BaseModel):
    id: int
    delegator_id: int
    delegate_id: int
    delegate_name: str = ""
    start_date: datetime
    end_date: datetime
    is_active: bool
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ===== 智能预审规则 =====

class RuleConfigCreate(BaseModel):
    rule_key: str = Field(..., min_length=1, max_length=64)
    rule_name: str = Field(..., min_length=1, max_length=128)
    document_type: Optional[str] = None
    rule_type: str = Field(..., pattern=r"^(budget_check|duplicate_check|field_range|field_required)$")
    field_key: Optional[str] = None
    operator: Optional[str] = None
    threshold_value: Optional[str] = None
    error_message: str = Field(..., min_length=1, max_length=256)
    severity: str = "error"
    is_active: bool = True
    priority: int = 0


class RuleConfigOut(BaseModel):
    id: int
    rule_key: str
    rule_name: str
    document_type: Optional[str]
    rule_type: str
    field_key: Optional[str]
    operator: Optional[str]
    threshold_value: Optional[str]
    error_message: str
    severity: str
    is_active: bool
    priority: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleCheckResult(BaseModel):
    rule_key: str
    rule_name: str
    passed: bool
    severity: str       # error / warning
    message: str
    field_key: Optional[str] = None


class RuleCheckResponse(BaseModel):
    record_id: int
    all_passed: bool
    results: list[RuleCheckResult]


# ===== 公告/制度文库 =====

class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., min_length=1)
    category: str = Field(..., pattern=r"^(announcement|policy|guide)$")
    document_type: Optional[str] = None
    is_pinned: bool = False


class AnnouncementOut(BaseModel):
    id: int
    title: str
    content: str
    category: str
    document_type: Optional[str] = None
    is_pinned: bool
    is_published: bool
    author_name: str = ""
    view_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ===== 资源管理 =====

class ResourceRoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    location: str = Field(..., min_length=1, max_length=256)
    capacity: int = 10
    equipment: str = ""


class ResourceRoomOut(BaseModel):
    id: int
    name: str
    location: str
    capacity: int
    equipment: str
    is_active: bool

    model_config = {"from_attributes": True}


class ResourceVehicleCreate(BaseModel):
    plate_number: str = Field(..., min_length=1, max_length=32)
    model: str = Field(..., min_length=1, max_length=64)
    seats: int = 5
    driver: str = ""


class ResourceVehicleOut(BaseModel):
    id: int
    plate_number: str
    model: str
    seats: int
    driver: str
    is_active: bool

    model_config = {"from_attributes": True}


class ResourceBookingCreate(BaseModel):
    resource_type: str = Field(..., pattern=r"^(meeting_room|vehicle)$")
    resource_id: int
    title: str = Field(..., min_length=1, max_length=256)
    start_time: str
    end_time: str
    participants: str = ""


class ResourceBookingOut(BaseModel):
    id: int
    resource_type: str
    resource_id: int
    resource_name: str = ""
    user_id: int
    username: str = ""
    title: str
    start_time: datetime
    end_time: datetime
    status: str
    participants: str
    reject_reason: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingApproveRequest(BaseModel):
    status: str = Field(..., pattern=r"^(approved|rejected)$")
    reject_reason: str = ""


# ===== 数据看板 =====

class DashboardStatsOut(BaseModel):
    # 概览
    total_users: int
    total_approvals: int
    pending_approvals: int
    today_new_approvals: int
    # 趋势
    approvals_by_day: list[dict]        # [{date, count}]
    approvals_by_type: list[dict]       # [{document_type, count}]
    approvals_by_status: dict           # {pending, approved, rejected, ...}
    # 效率
    avg_processing_hours: float
    approval_rate: float                # 通过率 0-1
    rejection_rate: float               # 驳回率 0-1
    # 排名
    top_departments: list[dict]         # [{department, total, approved, pending}]
    top_applicants: list[dict]          # [{username, count}]
