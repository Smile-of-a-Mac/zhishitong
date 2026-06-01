"""管理员路由 — API Key 管理 / 学校服务等级 / 成员管理"""
import datetime
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import (
    User, ApiKey, ApiKeyType, ApprovalRecord,
    AdminAuditLog, TierEnum, DeletedBy,
)
from schemas import (
    UserOut,
    ApiKeyCreate, ApiKeyOut,
    AuditLogOut,
)
from auth import require_admin, require_school_admin, hash_password, verify_password
from auth import set_test_override, clear_test_override, get_test_override
from auth import get_raw_user
from services.crypto_service import encrypt, decrypt
from config import MAX_OCR_KEYS, MAX_FILL_KEYS, MAX_LLM_KEYS
from services.logging_service import LogCategory, log
from services.key_pool import get_pool_stats
from services.file_service import delete_physical

router = APIRouter(prefix="/api/admin", tags=["admin"])


# =============================================================================
# 学校服务等级管理
# =============================================================================

class SchoolTierUpdate(BaseModel):
    tier: str = Field(..., pattern=r"^(free|pro)$")


class SchoolCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    tier: str = Field(..., pattern=r"^(free|pro)$")


@router.post("/schools")
def create_school(
    body: SchoolCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """创建新学校并自动生成管理员账户"""
    # 检查学校是否已存在
    existing = db.query(User).filter(User.school == body.name).first()
    if existing:
        raise HTTPException(400, f"学校 '{body.name}' 已存在")

    tier = TierEnum(body.tier)
    ocr_quota = 30 if tier == TierEnum.pro else 0

    initial_passwords: dict[str, str] = {}

    # 自动创建学校管理员
    school_password = secrets.token_urlsafe(10)
    # 将初始密码写入 hashed_password（不在响应中返回）
    school_admin = User(
        username=f"{body.name}_admin",
        hashed_password=hash_password(school_password),
        tier=tier, llm_ocr_quota=ocr_quota,
        is_school_admin=True,
        real_name=f"{body.name}管理员",
        school=body.name,
        department="学校办公室",
    )
    db.add(school_admin)
    initial_passwords[school_admin.username] = school_password

    # 自动创建部门管理员（计算机学院）
    dept_password = secrets.token_urlsafe(10)
    dept_admin = User(
        username=f"{body.name}_dept",
        hashed_password=hash_password(dept_password),
        tier=tier, llm_ocr_quota=ocr_quota,
        is_dept_admin=True,
        real_name=f"{body.name}部门管理员",
        school=body.name,
        department="计算机学院",
    )
    db.add(dept_admin)
    initial_passwords[dept_admin.username] = dept_password

    # 自动创建财务管理员
    finance_password = secrets.token_urlsafe(10)
    fin_admin = User(
        username=f"{body.name}_finance",
        hashed_password=hash_password(finance_password),
        tier=tier, llm_ocr_quota=ocr_quota,
        is_finance_admin=True,
        real_name=f"{body.name}财务管理员",
        school=body.name,
        department="财务处",
    )
    db.add(fin_admin)
    initial_passwords[fin_admin.username] = finance_password

    db.add(AdminAuditLog(
        admin_id=admin.id, action="create_school",
        target_type="school", target_id=None,
        detail=f"创建学校: {body.name} ({body.tier})",
    ))
    db.commit()

    log(LogCategory.ADMIN, "info",
        f"创建学校: {body.name} 层级: {body.tier}",
        user_id=admin.id, school=body.name)

    return {
        "detail": f"学校 '{body.name}' 已创建",
        "school": body.name,
        "tier": body.tier,
        "require_password_change": True,
        "accounts": [
            {"username": school_admin.username, "role": "学校管理员"},
            {"username": dept_admin.username, "role": "部门管理员"},
            {"username": fin_admin.username, "role": "财务管理员"},
        ],
        "secure_notice": "初始密码已随机生成，请通过安全渠道向管理员分发；或由管理员在后台「密码重置」功能中为各账号设置初始密码。",
    }


@router.get("/schools")
def list_schools(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """查看所有学校及其服务等级"""
    schools: dict[str, dict] = {}
    users = db.query(User).filter(
        User.school.isnot(None), User.school != "",
    ).all()
    for u in users:
        if u.school not in schools:
            schools[u.school] = {"school": u.school, "tier": u.tier.value, "user_count": 0}
        schools[u.school]["user_count"] += 1
    return sorted(schools.values(), key=lambda s: s["school"])


@router.put("/schools/{school_name}/tier")
def update_school_tier(
    school_name: str,
    body: SchoolTierUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """修改学校服务等级（全员统一变更层级和配额）"""
    users = db.query(User).filter(
        User.school == school_name,
        ~User.is_admin,  # 不修改 admin
    ).all()
    if not users:
        raise HTTPException(404, f"未找到学校: {school_name}")

    new_tier = TierEnum(body.tier)
    ocr_quota = 30 if new_tier == TierEnum.pro else 0

    for u in users:
        u.tier = new_tier
        u.llm_ocr_quota = ocr_quota
        u.llm_ocr_used = 0

    db.add(AdminAuditLog(
        admin_id=admin.id, action="update_school_tier",
        target_type="school", target_id=None,
        detail=f"学校 {school_name} 层级变更: {new_tier.value}",
    ))
    db.commit()

    log(LogCategory.ADMIN, "info",
        f"学校层级变更: {school_name} → {new_tier.value}",
        user_id=admin.id, school=school_name, tier=new_tier.value)

    return {"detail": f"学校 {school_name} 已切换为 {new_tier.value} 版, 影响 {len(users)} 名用户"}


# =============================================================================
# 成员管理（添加/删除/权限调整）
# =============================================================================

class MemberCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    real_name: Optional[str] = None
    school: str = Field(..., min_length=1, max_length=128)
    department: Optional[str] = None
    is_school_admin: bool = False
    is_dept_admin: bool = False
    is_finance_admin: bool = False


class MemberRolesUpdate(BaseModel):
    is_school_admin: Optional[bool] = None
    is_dept_admin: Optional[bool] = None
    is_finance_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    department: Optional[str] = None
    real_name: Optional[str] = None
    school: Optional[str] = None


class MemberUpdate(BaseModel):
    """成员信息全面更新"""
    real_name: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    school: Optional[str] = None
    student_id: Optional[str] = None
    major: Optional[str] = None
    class_name: Optional[str] = None
    enrollment_year: Optional[int] = None
    advisor: Optional[str] = None
    employee_id: Optional[str] = None
    title: Optional[str] = None
    is_school_admin: Optional[bool] = None
    is_dept_admin: Optional[bool] = None
    is_finance_admin: Optional[bool] = None
    is_active: Optional[bool] = None


@router.get("/members", response_model=list[UserOut])
def list_members(
    school: Optional[str] = Query(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """查看某学校的所有成员（非 admin）"""
    q = db.query(User).filter(~User.is_admin)
    if school:
        q = q.filter(User.school == school)
    return [UserOut.model_validate(u) for u in q.order_by(User.school, User.username).all()]


@router.post("/members", response_model=UserOut)
def create_member(
    body: MemberCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """在指定学校内创建新成员"""
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, "用户名已存在")

    # 确定 tier（按学校套餐）
    school_user = db.query(User).filter(
        User.school == body.school, ~User.is_admin,
    ).first()
    if not school_user:
        raise HTTPException(400, f"学校不存在或无用户: {body.school}")
    tier = school_user.tier
    ocr_quota = 30 if tier == TierEnum.pro else 0

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        tier=tier, llm_ocr_quota=ocr_quota,
        real_name=body.real_name,
        school=body.school,
        department=body.department,
        is_school_admin=body.is_school_admin,
        is_dept_admin=body.is_dept_admin,
        is_finance_admin=body.is_finance_admin,
    )
    db.add(user)
    db.add(AdminAuditLog(
        admin_id=admin.id, action="create_member",
        target_type="user", target_id=None,
        detail=f"创建成员 {body.username} @ {body.school}",
    ))
    db.commit()
    db.refresh(user)

    log(LogCategory.ADMIN, "info",
        f"创建成员: {user.username} @ {body.school}",
        user_id=admin.id, school=body.school)

    return UserOut.model_validate(user)


@router.put("/members/{user_id}/roles", response_model=UserOut)
def update_member_roles(
    user_id: int,
    body: MemberRolesUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """调整成员的权限角色"""
    target = db.query(User).filter(User.id == user_id, ~User.is_admin).first()
    if not target:
        raise HTTPException(404, "成员不存在")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(target, field, value)

    db.add(AdminAuditLog(
        admin_id=admin.id, action="update_member_roles",
        target_type="user", target_id=user_id,
        detail=f"更新角色: {target.username}",
    ))
    db.commit()
    db.refresh(target)

    log(LogCategory.ADMIN, "info",
        f"更新成员角色: {target.username}",
        user_id=admin.id, target_user_id=user_id)

    return UserOut.model_validate(target)


@router.delete("/members/{user_id}")
def delete_member(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """从学校中移除成员（软删除）"""
    target = db.query(User).filter(User.id == user_id, ~User.is_admin).first()
    if not target:
        raise HTTPException(404, "成员不存在")

    target.is_active = False

    db.add(AdminAuditLog(
        admin_id=admin.id, action="delete_member",
        target_type="user", target_id=user_id,
        detail=f"移除成员: {target.username} @ {target.school}",
    ))
    db.commit()

    log(LogCategory.ADMIN, "warning",
        f"移除成员: {target.username} @ {target.school}",
        user_id=admin.id, target_user_id=user_id)

    return {"detail": f"成员 {target.username} 已移除"}


@router.put("/members/{user_id}/restore")
def restore_member(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """恢复被移除的成员"""
    target = db.query(User).filter(User.id == user_id, ~User.is_admin).first()
    if not target:
        raise HTTPException(404, "成员不存在")

    target.is_active = True

    db.add(AdminAuditLog(
        admin_id=admin.id, action="restore_member",
        target_type="user", target_id=user_id,
        detail=f"恢复成员: {target.username}",
    ))
    db.commit()

    log(LogCategory.ADMIN, "info",
        f"恢复成员: {target.username}",
        user_id=admin.id, target_user_id=user_id)

    return {"detail": f"成员 {target.username} 已恢复"}


# ---- 更新成员信息 ----

@router.put("/members/{user_id}")
def update_member(
    user_id: int,
    body: MemberUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """更新成员信息（姓名/部门/学校/角色/状态）"""
    target = db.query(User).filter(User.id == user_id, ~User.is_admin).first()
    if not target:
        raise HTTPException(404, "成员不存在")

    changed = []
    all_fields = [
        "real_name", "gender", "phone", "email", "department", "school",
        "student_id", "major", "class_name", "enrollment_year",
        "advisor", "employee_id", "title",
        "is_school_admin", "is_dept_admin", "is_finance_admin", "is_active",
    ]
    for field in all_fields:
        val = getattr(body, field, None)
        if val is not None:
            setattr(target, field, val)
            changed.append(field)

    if changed:
        db.add(AdminAuditLog(
            admin_id=admin.id, action="update_member",
            target_type="user", target_id=user_id,
            detail=f"更新成员 {target.username}: {', '.join(changed)}",
        ))
        db.commit()
        log(LogCategory.ADMIN, "info",
            f"更新成员: {target.username} ({', '.join(changed)})",
            user_id=admin.id, target_user_id=user_id)

    return UserOut.model_validate(target)


# ---- 硬删除成员 ----

@router.delete("/members/{user_id}/hard")
def hard_delete_member(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """永久删除成员（物理删除，不可恢复）"""
    target = db.query(User).filter(User.id == user_id, ~User.is_admin).first()
    if not target:
        raise HTTPException(404, "成员不存在")
    if target.is_active:
        raise HTTPException(400, "请先禁用成员再删除")

    username = target.username
    # 先删关联数据
    from models import ApprovalRecord, QuotaLog
    db.query(QuotaLog).filter(QuotaLog.user_id == user_id).delete()
    db.query(ApprovalRecord).filter(ApprovalRecord.user_id == user_id).delete()
    db.delete(target)

    db.add(AdminAuditLog(
        admin_id=admin.id, action="hard_delete_member",
        target_type="user", target_id=user_id,
        detail=f"永久删除成员: {username}",
    ))
    db.commit()

    log(LogCategory.ADMIN, "warning",
        f"永久删除成员: {username}",
        user_id=admin.id, target_user_id=user_id)

    return {"detail": f"成员 {username} 已永久删除"}


# ---- 管理员重置成员密码 ----

class AdminResetPassword(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=128)


@router.put("/members/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    body: AdminResetPassword,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员重置指定成员的密码"""
    target = db.query(User).filter(User.id == user_id, ~User.is_admin).first()
    if not target:
        raise HTTPException(404, "成员不存在")
    target.hashed_password = hash_password(body.new_password)
    db.add(AdminAuditLog(
        admin_id=admin.id, action="reset_password",
        target_type="user", target_id=user_id,
        detail=f"重置密码: {target.username}",
    ))
    db.commit()
    log(LogCategory.ADMIN, "warning",
        f"管理员重置密码: {target.username}",
        user_id=admin.id, target_user_id=user_id)
    return {"detail": f"已重置 {target.username} 的密码"}


# =============================================================================
# API Key 管理（保留）
# =============================================================================

@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(
    key_type: str = Query(None, pattern="^(ocr|json_fill|llm)$"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(ApiKey)
    if key_type:
        q = q.filter(ApiKey.key_type == ApiKeyType(key_type))
    return [ApiKeyOut.model_validate(k) for k in q.order_by(ApiKey.created_at.desc()).all()]


@router.post("/api-keys", response_model=ApiKeyOut)
def add_api_key(
    body: ApiKeyCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # 数量限制
    ktype = ApiKeyType(body.key_type)
    count = db.query(ApiKey).filter(ApiKey.key_type == ktype).count()
    limit_map = {"ocr": MAX_OCR_KEYS, "json_fill": MAX_FILL_KEYS, "llm": MAX_LLM_KEYS}
    limit = limit_map.get(body.key_type, 100)
    if count >= limit:
        raise HTTPException(400, f"{body.key_type} 类型 Key 已达上限 {limit} 个")

    encrypted = encrypt(body.api_key_plain)
    key = ApiKey(
        key_type=ktype,
        provider=body.provider,
        api_base=body.api_base,
        api_key_encrypted=encrypted,
        default_model=body.default_model,
        created_by=admin.id,
        note=body.note,
    )
    db.add(key)
    db.add(AdminAuditLog(
        admin_id=admin.id, action="add_api_key",
        target_type="api_key", target_id=None,
        detail=f"{body.key_type} / {body.provider} / {body.default_model}",
    ))
    db.commit()
    db.refresh(key)

    log(LogCategory.ADMIN, "info", f"添加 API Key: {body.provider}/{body.default_model}",
        user_id=admin.id, key_type=body.key_type, provider=body.provider, model=body.default_model)

    return ApiKeyOut.model_validate(key)


@router.delete("/api-keys/{key_id}")
def disable_api_key(
    key_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """停用 Key（软禁，保留记录）"""
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not key:
        raise HTTPException(404, "Key 不存在")
    old_active = key.is_active
    key.is_active = False
    db.add(AdminAuditLog(
        admin_id=admin.id, action="disable_api_key",
        target_type="api_key", target_id=key_id,
        detail=f"停用 {key.provider}/{key.default_model}",
    ))
    db.commit()

    log(LogCategory.ADMIN, "info", f"停用 API Key #{key_id}: {key.provider}/{key.default_model}",
        user_id=admin.id, key_id=key_id, provider=key.provider, model=key.default_model)

    return {"detail": "Key 已停用"}


@router.put("/api-keys/{key_id}/restore")
def restore_api_key(
    key_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """重新启用已停用的 Key"""
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not key:
        raise HTTPException(404, "Key 不存在")
    key.is_active = True
    key.fail_count = 0
    db.add(AdminAuditLog(
        admin_id=admin.id, action="restore_api_key",
        target_type="api_key", target_id=key_id,
        detail=f"重新启用 {key.provider}/{key.default_model}",
    ))
    db.commit()

    log(LogCategory.ADMIN, "info", f"重新启用 API Key #{key_id}: {key.provider}/{key.default_model}",
        user_id=admin.id, key_id=key_id, provider=key.provider, model=key.default_model)

    return {"detail": "Key 已重新启用"}


@router.delete("/api-keys/{key_id}/hard")
def hard_delete_api_key(
    key_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """物理删除 Key（不可恢复）"""
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not key:
        raise HTTPException(404, "Key 不存在")

    provider_info = f"{key.provider}/{key.default_model}"
    # 审计日志（在删除前记录）
    db.add(AdminAuditLog(
        admin_id=admin.id, action="hard_delete_api_key",
        target_type="api_key", target_id=key_id,
        detail=f"物理删除 {provider_info} (密文已销毁)",
    ))
    db.delete(key)
    db.commit()

    log(LogCategory.ADMIN, "warning", f"物理删除 API Key #{key_id}: {provider_info}",
        user_id=admin.id, key_id=key_id, provider=key.provider)

    return {"detail": f"Key '{provider_info}' 已永久删除"}


# ========== 审计日志 ==========

@router.get("/audit", response_model=list[AuditLogOut])
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [AuditLogOut.model_validate(l) for l in logs]


# ========== 学校管理员 — 部门管理员管理 ==========

class DeptAdminCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    department: str = Field(..., min_length=1, max_length=64)


class DeptAdminUpdate(BaseModel):
    department: Optional[str] = Field(None, min_length=1, max_length=64)
    is_active: Optional[bool] = None


@router.get("/dept-admins", response_model=list[UserOut])
def list_dept_admins(
    admin: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    """学校管理员查看本校部门管理员"""
    q = db.query(User).filter(User.is_dept_admin == True)
    if not admin.is_admin:
        q = q.filter(User.school == admin.school)  # 学校隔离
    return [UserOut.model_validate(u) for u in q.order_by(User.department, User.username).all()]


@router.post("/dept-admins", response_model=UserOut)
def create_dept_admin(
    body: DeptAdminCreate,
    admin: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    """学校管理员创建部门管理员账号"""
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, "用户名已存在")

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        tier=TierEnum.free,
        llm_ocr_quota=0,
        is_dept_admin=True,
        department=body.department,
        school=admin.school,  # 继承学校管理员的学校
    )
    db.add(user)
    db.add(AdminAuditLog(
        admin_id=admin.id, action="create_dept_admin",
        target_type="user", target_id=None,
        detail=f"创建部门管理员: {body.username} ({body.department})",
    ))
    db.commit()
    db.refresh(user)

    log(LogCategory.ADMIN, "info",
        f"创建部门管理员: {body.username} 部门: {body.department}",
        user_id=admin.id, target_username=body.username)

    return UserOut.model_validate(user)


@router.put("/dept-admins/{user_id}", response_model=UserOut)
def update_dept_admin(
    user_id: int,
    body: DeptAdminUpdate,
    admin: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    """学校管理员编辑本校部门管理员（部门/状态）"""
    q = db.query(User).filter(User.id == user_id, User.is_dept_admin == True)
    if not admin.is_admin:
        q = q.filter(User.school == admin.school)  # 学校隔离
    target = q.first()
    if not target:
        raise HTTPException(404, "部门管理员不存在")

    if body.department is not None:
        target.department = body.department
    if body.is_active is not None:
        target.is_active = body.is_active

    db.add(AdminAuditLog(
        admin_id=admin.id, action="update_dept_admin",
        target_type="user", target_id=target.id,
        detail=f"更新部门管理员: {target.username}",
    ))
    db.commit()
    db.refresh(target)

    log(LogCategory.ADMIN, "info",
        f"更新部门管理员: {target.username}",
        user_id=admin.id, target_user_id=target.id)

    return UserOut.model_validate(target)


@router.delete("/dept-admins/{user_id}")
def delete_dept_admin(
    user_id: int,
    admin: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    """学校管理员删除本校部门管理员（软删除）"""
    q = db.query(User).filter(User.id == user_id, User.is_dept_admin == True)
    if not admin.is_admin:
        q = q.filter(User.school == admin.school)  # 学校隔离
    target = q.first()
    if not target:
        raise HTTPException(404, "部门管理员不存在")

    target.is_active = False
    target.is_dept_admin = False
    target.department = None

    db.add(AdminAuditLog(
        admin_id=admin.id, action="delete_dept_admin",
        target_type="user", target_id=target.id,
        detail=f"删除部门管理员: {target.username}",
    ))
    db.commit()

    log(LogCategory.ADMIN, "info",
        f"删除部门管理员: {target.username}",
        user_id=admin.id, target_user_id=target.id)

    return {"detail": f"部门管理员 {target.username} 已删除"}


# ========== 学校管理员 — 学校字段管理 ==========

class UserSchoolUpdate(BaseModel):
    school: str = Field(..., min_length=1, max_length=128)


@router.put("/users/{user_id}/school", response_model=UserOut)
def set_user_school(
    user_id: int,
    body: UserSchoolUpdate,
    admin: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    """学校管理员为校内用户设置学校字段"""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "用户不存在")
    if target.is_admin:
        raise HTTPException(400, "不能修改信息管理员的学校字段")
    # 非超级管理员只能操作本校用户
    if not admin.is_admin and target.school != admin.school:
        raise HTTPException(403, "只能操作本校用户")

    old_school = target.school
    target.school = body.school.strip()

    db.add(AdminAuditLog(
        admin_id=admin.id, action="set_user_school",
        target_type="user", target_id=target.id,
        detail=f"学校字段: {old_school} → {target.school}",
    ))
    db.commit()
    db.refresh(target)

    log(LogCategory.ADMIN, "info",
        f"设置用户学校字段: {target.username} {old_school} → {target.school}",
        user_id=admin.id, target_user_id=target.id, old_school=old_school,
        new_school=target.school)

    return UserOut.model_validate(target)


# ========== 信息管理员 — 数据管理 ==========

@router.get("/data")
def list_all_data(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    school: Optional[str] = Query(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """信息管理员查看全部审批数据（IT 运维向，不参与审批）"""
    q = db.query(ApprovalRecord).filter(ApprovalRecord.hard_deleted == False)

    if status == "active":
        q = q.filter(ApprovalRecord.is_deleted == False)
    elif status == "deleted":
        q = q.filter(ApprovalRecord.is_deleted == True)

    if username or school:
        q = q.join(User, ApprovalRecord.user_id == User.id)
        if username:
            q = q.filter(User.username.ilike(f"%{username}%"))
        if school:
            q = q.filter(User.school == school)

    total = q.count()
    records = (
        q.order_by(ApprovalRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for r in records:
        u = db.query(User).filter(User.id == r.user_id).first()
        items.append({
            "id": r.id,
            "username": u.username if u else "unknown",
            "original_filename": r.original_filename,
            "document_type": r.document_type,
            "status": r.status.value if r.status else "unknown",
            "is_deleted": r.is_deleted,
            "deleted_by": r.deleted_by.value if r.deleted_by else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {"items": items, "total": total}


@router.put("/data/{record_id}/restore")
def restore_record(
    record_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """恢复软删除的审批记录"""
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id,
        ApprovalRecord.hard_deleted == False,
        ApprovalRecord.is_deleted == True,
    ).first()
    if not record:
        raise HTTPException(404, "记录不存在或未删除")

    record.is_deleted = False
    record.deleted_by = None
    record.deleted_at = None

    db.add(AdminAuditLog(
        admin_id=admin.id, action="restore_record",
        target_type="approval_record", target_id=record.id,
        detail=f"恢复记录 #{record.id}",
    ))
    db.commit()

    log(LogCategory.ADMIN, "info", f"恢复记录 #{record.id}", user_id=admin.id, record_id=record.id)
    return {"detail": "已恢复"}


@router.delete("/data/{record_id}")
def hard_delete_record(
    record_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """物理删除审批记录（不可恢复）"""
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id,
        ApprovalRecord.hard_deleted == False,
    ).first()
    if not record:
        raise HTTPException(404, "记录不存在")

    if record.storage_path:
        try:
            delete_physical(record.storage_path)
        except HTTPException:
            raise
        except Exception as exc:
            log(LogCategory.ADMIN, "warning", "物理文件删除失败", user_id=admin.id, record_id=record.id, error=str(exc))

    record.hard_deleted = True
    record.is_deleted = True

    db.add(AdminAuditLog(
        admin_id=admin.id, action="hard_delete_record",
        target_type="approval_record", target_id=record.id,
        detail=f"物理删除记录 #{record.id}",
    ))
    db.commit()

    log(LogCategory.ADMIN, "warning", f"物理删除记录 #{record.id}", user_id=admin.id, record_id=record.id)
    return {"detail": "已永久删除"}


# ===== Key 池统计 =====

@router.get("/key-pool/stats")
def key_pool_stats(
    key_type: str = Query(None, pattern="^(ocr|json_fill|llm)$"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    查看 Key 池统计信息。
    不指定 key_type 时返回所有类型的汇总。
    """
    if key_type:
        return get_pool_stats(db, ApiKeyType(key_type))
    return {
        "pools": [
            get_pool_stats(db, ApiKeyType(t))
            for t in ["ocr", "json_fill", "llm"]
        ]
    }


# ==============================
# 测试模拟面板（管理员专用）
# ==============================

class TestSessionOverride(BaseModel):
    tier: Optional[str] = None          # free | pro | pro_plus
    is_admin: Optional[bool] = None
    is_dept_admin: Optional[bool] = None
    is_school_admin: Optional[bool] = None
    is_finance_admin: Optional[bool] = None
    department: Optional[str] = None
    school: Optional[str] = None
    reset: bool = False                  # True = 清除所有覆盖


@router.get("/test-session")
def get_test_session(
    raw: User = Depends(get_raw_user),
):
    """获取当前测试模拟状态（绕过覆盖，管理员始终可查）"""
    if not raw.is_admin:
        raise HTTPException(403, "需要管理员权限")
    override = get_test_override(raw.id)
    return {
        "active": override is not None,
        "overrides": override or {},
        "original": {
            "username": raw.username,
            "tier": raw.tier.value,
            "is_admin": raw.is_admin,
            "is_dept_admin": raw.is_dept_admin,
            "is_school_admin": raw.is_school_admin,
            "is_finance_admin": raw.is_finance_admin,
            "department": raw.department,
            "school": raw.school,
        },
    }


@router.post("/test-session")
def set_test_session(
    body: TestSessionOverride,
    raw: User = Depends(get_raw_user),
):
    """设置测试模拟覆盖"""
    if not raw.is_admin:
        raise HTTPException(403, "需要管理员权限")
    if body.reset:
        clear_test_override(raw.id)
        log(LogCategory.ADMIN, "info", "测试模拟: 已清除",
            user_id=raw.id)
        return {"active": False, "message": "已恢复原始身份"}

    overrides = {}
    if body.tier is not None:
        if body.tier not in ("free", "pro", "pro_plus"):
            raise HTTPException(400, f"无效订阅层级: {body.tier}")
        overrides["tier"] = body.tier
    for field in ("is_admin", "is_dept_admin", "is_school_admin", "is_finance_admin"):
        if getattr(body, field) is not None:
            overrides[field] = getattr(body, field)
    if body.department is not None:
        overrides["department"] = body.department
    if body.school is not None:
        overrides["school"] = body.school

    if not overrides:
        raise HTTPException(400, "请至少设置一个覆盖字段，或设置 reset=true 清除")

    set_test_override(raw.id, overrides)
    log(LogCategory.ADMIN, "info",
        f"测试模拟: {', '.join(f'{k}={v}' for k, v in overrides.items())}",
        user_id=raw.id, **overrides)
    return {"active": True, "overrides": overrides, "message": "模拟已激活，刷新页面生效"}


@router.delete("/test-session")
def delete_test_session(
    raw: User = Depends(get_raw_user),
):
    """清除测试模拟"""
    if not raw.is_admin:
        raise HTTPException(403, "需要管理员权限")
    clear_test_override(raw.id)
    log(LogCategory.ADMIN, "info", "测试模拟: 已清除", user_id=raw.id)
    return {"active": False, "message": "已恢复原始身份"}
