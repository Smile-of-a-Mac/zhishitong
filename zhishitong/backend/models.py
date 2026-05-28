"""数据模型 — 用户·API Key池·审批记录·审计日志·通知·规则引擎·资源预约"""
import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, Enum as SAEnum,
    ForeignKey, Float,
)
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()


# ===== 枚举 =====

class TierEnum(str, enum.Enum):
    free = "free"
    pro = "pro"
    pro_plus = "pro_plus"


class ApiKeyType(str, enum.Enum):
    ocr = "ocr"
    json_fill = "json_fill"
    llm = "llm"  # RAG/AI 服务的通用 LLM Key


class ApprovalStatus(str, enum.Enum):
    pending = "pending"             # 已提交，待人工审核
    approved = "approved"           # 审批通过
    rejected = "rejected"           # 审批驳回
    needs_revision = "needs_revision"  # 需修改补交
    cancelled = "cancelled"         # 已取消/结案
    withdrawn = "withdrawn"         # 用户撤回（可重新编辑提交）


class DeletedBy(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class NotificationType(str, enum.Enum):
    approval_submitted = "approval_submitted"     # 申请已提交（通知审批人）
    approval_approved = "approval_approved"       # 审批通过
    approval_rejected = "approval_rejected"       # 审批驳回
    approval_needs_revision = "approval_needs_revision"  # 需修改
    approval_urged = "approval_urged"             # 被催办
    approval_overdue = "approval_overdue"         # 超时未处理
    stage_advanced = "stage_advanced"             # 进入下一审批阶段
    system_announcement = "system_announcement"   # 系统公告


class ResourceType(str, enum.Enum):
    meeting_room = "meeting_room"
    vehicle = "vehicle"


class BookingStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


# ===== 用户表 =====

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    tier = Column(SAEnum(TierEnum), default=TierEnum.free, nullable=False)
    llm_ocr_quota = Column(Integer, default=0)     # Pro 每月配额
    llm_ocr_used = Column(Integer, default=0)      # 当月已用
    quota_reset_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)          # 超级管理员
    is_school_admin = Column(Boolean, default=False)   # 学校管理员（管理各部门管理员，不提交请求）
    is_dept_admin = Column(Boolean, default=False)     # 部门事务管理员（只审批，不提交请求）
    is_finance_admin = Column(Boolean, default=False)  # 财务管理员（审批报销财务环节）
    department = Column(String(64), nullable=True)     # 所属部门（如：计算机学院、财务处）
    school = Column(String(128), nullable=True)        # 所属学校（甲方是学校，层级按学校决定）
    # ── 个人信息（学生/教师通用） ──
    real_name = Column(String(64), nullable=True)      # 真实姓名
    gender = Column(String(8), nullable=True)          # 性别
    phone = Column(String(20), nullable=True)          # 联系电话
    email = Column(String(128), nullable=True)         # 电子邮箱
    # ── 学生专属 ──
    student_id = Column(String(32), nullable=True)     # 学号
    major = Column(String(64), nullable=True)          # 专业
    class_name = Column(String(64), nullable=True)     # 班级
    enrollment_year = Column(Integer, nullable=True)   # 入学年份
    advisor = Column(String(64), nullable=True)        # 辅导员
    # ── 教师专属 ──
    employee_id = Column(String(32), nullable=True)    # 工号
    title = Column(String(32), nullable=True)           # 职称（教授/副教授/讲师/助教）
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    approvals = relationship("ApprovalRecord", back_populates="user")
    quota_logs = relationship("QuotaLog", back_populates="user", order_by="QuotaLog.created_at.desc()")


# ===== 配额流水 =====

class QuotaLog(Base):
    __tablename__ = "quota_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(32))      # llm_ocr | llm_fill | quota_reset | tier_upgrade
    detail = Column(String(256))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="quota_logs")


# ===== API Key 池 =====

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key_type = Column(SAEnum(ApiKeyType), nullable=False)
    provider = Column(String(64), nullable=False)
    api_base = Column(String(256), nullable=False)
    api_key_encrypted = Column(String(512), nullable=False)  # Fernet 密文
    default_model = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)   # 累计使用次数
    fail_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    note = Column(String(256), default="")


# ===== 审批记录（核心业务表） =====

class ApprovalRecord(Base):
    __tablename__ = "approval_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 文件
    original_filename = Column(String(256))
    storage_path = Column(String(512), nullable=False)
    mime_type = Column(String(64))
    file_size = Column(Integer)

    # OCR & 填充
    ocr_provider = Column(String(32))
    ocr_model = Column(String(128))
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=True)
    raw_ocr_text = Column(Text)
    filled_json = Column(Text)

    # 审批
    document_type = Column(String(32))
    status = Column(SAEnum(ApprovalStatus), default=ApprovalStatus.pending, index=True)
    decision_reason = Column(Text)       # LLM 分析摘要 / 最后处理意见
    policy_refs = Column(Text)           # 引用的规则条文
    suggestions = Column(Text)           # LLM 修改建议
    missing_info = Column(Text)          # LLM 标记的缺失信息

    # 多阶段审批
    current_stage = Column(String(32), default="dept_review", nullable=False)  # 当前阶段
    stage_history_json = Column(Text, default="[]")                            # 阶段历史 JSON

    # 软删除
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_by = Column(SAEnum(DeletedBy), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    hard_deleted = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="approvals")


# ===== 审计日志 =====

class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(64), nullable=False)
    target_type = Column(String(64), nullable=False)
    target_id = Column(Integer, nullable=True)
    detail = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


# ===== 系统运行日志（结构化） =====

class SystemLog(Base):
    """结构化运行日志，用于管理员监控面板和故障排查"""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(32), nullable=False, index=True)   # auth/ocr/approval/admin/system/inference
    level = Column(String(16), nullable=False, index=True)       # debug/info/warning/error/critical
    message = Column(String(512), nullable=False)
    user_id = Column(Integer, nullable=True)
    record_id = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)                 # 操作耗时（毫秒）
    error_trace = Column(Text, default="")                       # 异常堆栈
    extra_json = Column(Text, default="{}")                      # 附加信息 JSON
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


# ===== 站内信通知 =====

class Notification(Base):
    """站内信通知，支持已读/未读，按用户推送"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(SAEnum(NotificationType), nullable=False)
    title = Column(String(128), nullable=False)
    body = Column(String(512), nullable=False)
    record_id = Column(Integer, ForeignKey("approval_records.id"), nullable=True)  # 关联审批记录
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", backref="notifications")


# ===== 审批意见模板 =====

class ApprovalOpinionTemplate(Base):
    """审批常用语模板，审批人可一键填入"""
    __tablename__ = "approval_opinion_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String(32), default="general")  # general/approve/reject/revision
    content = Column(String(256), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ===== 审批代理 =====

class ApprovalDelegation(Base):
    """审批人休假/出差时可将审批权委托给他人"""
    __tablename__ = "approval_delegations"

    id = Column(Integer, primary_key=True, index=True)
    delegator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # 委托人
    delegate_id = Column(Integer, ForeignKey("users.id"), nullable=False)               # 被委托人
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    reason = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    delegator = relationship("User", foreign_keys=[delegator_id], backref="delegations_given")
    delegate = relationship("User", foreign_keys=[delegate_id], backref="delegations_received")


# ===== 智能预审规则引擎 =====

class RuleConfig(Base):
    """可配置的自动预审规则，在 LLM 分析之前执行硬性检查"""
    __tablename__ = "rule_configs"

    id = Column(Integer, primary_key=True, index=True)
    rule_key = Column(String(64), unique=True, nullable=False)       # 规则唯一标识
    rule_name = Column(String(128), nullable=False)                  # 规则中文名
    document_type = Column(String(32), nullable=True)                # 适用文档类型（null=全局）
    rule_type = Column(String(32), nullable=False)                   # budget_check / duplicate_check / field_range / field_required
    field_key = Column(String(64), nullable=True)                    # 校验字段 key
    operator = Column(String(16), nullable=True)                     # gt/lt/gte/lte/eq/contains
    threshold_value = Column(String(128), nullable=True)             # 阈值
    error_message = Column(String(256), nullable=False)              # 不通过时的提示语
    severity = Column(String(16), default="error")                   # error=拦截 / warning=提醒
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)                            # 优先级，数字越大越先执行
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


# ===== 公告 / 制度文库 =====

class Announcement(Base):
    """系统公告和校规制度文库"""
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(32), nullable=False, index=True)   # announcement / policy / guide
    document_type = Column(String(32), nullable=True)            # 关联的审批类型（可选）
    is_pinned = Column(Boolean, default=False)                   # 置顶
    is_published = Column(Boolean, default=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    author = relationship("User", backref="announcements")


# ===== 资源管理 — 会议室 =====

class ResourceRoom(Base):
    """可预约的会议室"""
    __tablename__ = "resource_rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)                 # 会议室名称
    location = Column(String(256), nullable=False)             # 位置
    capacity = Column(Integer, default=10)                     # 容纳人数
    equipment = Column(String(256), default="")                # 设备（投影仪/白板/视频会议）
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ===== 资源管理 — 车辆 =====

class ResourceVehicle(Base):
    """可预约的公车"""
    __tablename__ = "resource_vehicles"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String(32), nullable=False)          # 车牌号
    model = Column(String(64), nullable=False)                 # 车型
    seats = Column(Integer, default=5)                         # 座位数
    driver = Column(String(32), default="")                    # 司机
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ===== 资源预约记录 =====

class ResourceBooking(Base):
    """会议室/车辆预约记录"""
    __tablename__ = "resource_bookings"

    id = Column(Integer, primary_key=True, index=True)
    resource_type = Column(SAEnum(ResourceType), nullable=False)
    resource_id = Column(Integer, nullable=False)              # room_id 或 vehicle_id
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(256), nullable=False)                # 预约事由
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(SAEnum(BookingStatus), default=BookingStatus.pending)
    participants = Column(String(512), default="")             # 参与人员（逗号分隔）
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 审批人
    reject_reason = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", foreign_keys=[user_id], backref="resource_bookings")
    approver = relationship("User", foreign_keys=[approver_id])
