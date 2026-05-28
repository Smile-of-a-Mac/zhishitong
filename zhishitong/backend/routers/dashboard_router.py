"""数据看板 API — 为各级管理员提供统计概览"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
from database import SessionLocal
from auth import get_current_user
from models import User, ApprovalRecord, ApprovalStatus, Notification

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/overview")
def dashboard_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """数据看板概览（按角色展示不同维度）"""
    now = _utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    days_30_ago = now - timedelta(days=30)

    is_dept = current_user.is_dept_admin
    is_finance = current_user.is_finance_admin
    is_school = current_user.is_school_admin
    is_super = current_user.is_admin

    # ── 基础查询基类 ──
    base_q = db.query(ApprovalRecord).filter(ApprovalRecord.is_deleted == False)

    # 部门管理员只看本部门
    if is_dept and current_user.department:
        base_q = base_q.join(User, ApprovalRecord.user_id == User.id).filter(
            User.department == current_user.department
        )
    # 财务管理员只看报销类
    elif is_finance:
        base_q = base_q.filter(ApprovalRecord.document_type == "reimbursement")
    # 学校管理员看本校
    elif is_school and current_user.school:
        base_q = base_q.join(User, ApprovalRecord.user_id == User.id).filter(
            User.school == current_user.school
        )
    # 超级管理员看全部（不做过滤）
    elif is_super:
        pass
    # 普通用户只看自己
    else:
        base_q = base_q.filter(ApprovalRecord.user_id == current_user.id)

    # ── 概览数字 ──
    total_approvals = base_q.count()
    pending_approvals = base_q.filter(ApprovalRecord.status == ApprovalStatus.pending).count()
    today_new = base_q.filter(ApprovalRecord.created_at >= today_start).count()

    total_users = db.query(User).filter(User.is_active == True).count()

    # ── 按日趋势（最近30天） ──
    daily_stats = []
    for i in range(30):
        day = today_start - timedelta(days=29 - i)
        day_start = day
        day_end = day + timedelta(days=1)
        count = base_q.filter(
            ApprovalRecord.created_at >= day_start,
            ApprovalRecord.created_at < day_end,
        ).count()
        daily_stats.append({"date": day.strftime("%m-%d"), "count": count})

    # ── 按类型分布 ──
    type_stats = (
        db.query(
            ApprovalRecord.document_type,
            func.count(ApprovalRecord.id).label("count"),
        )
        .filter(ApprovalRecord.is_deleted == False)
    )
    if is_dept and current_user.department:
        type_stats = type_stats.join(User, ApprovalRecord.user_id == User.id).filter(
            User.department == current_user.department
        )
    type_stats = type_stats.group_by(ApprovalRecord.document_type).all()
    type_list = [{"document_type": t or "unknown", "count": c} for t, c in type_stats]

    # ── 状态分布 ──
    status_stats = {}
    for s in ApprovalStatus:
        q = base_q.filter(ApprovalRecord.status == s)
        status_stats[s.value] = q.count()

    # ── 效率指标 ──
    approved_count = status_stats.get("approved", 0)
    rejected_count = status_stats.get("rejected", 0)
    total_decided = approved_count + rejected_count
    approval_rate = round(approved_count / total_decided, 3) if total_decided > 0 else 0
    rejection_rate = round(rejected_count / total_decided, 3) if total_decided > 0 else 0

    # 平均处理时长（从创建到最新更新）
    avg_hours = 0
    avg_result = base_q.filter(
        ApprovalRecord.status.in_([ApprovalStatus.approved, ApprovalStatus.rejected])
    ).with_entities(
        func.avg(
            func.julianday(ApprovalRecord.updated_at) - func.julianday(ApprovalRecord.created_at)
        )
    ).scalar()
    if avg_result:
        avg_hours = round(float(avg_result) * 24, 1)

    # ── 部门排名（仅学校/超级管理员可见） ──
    top_departments = []
    if is_school or is_super:
        dept_stats = (
            db.query(
                User.department,
                func.count(ApprovalRecord.id).label("total"),
                func.sum(case((ApprovalRecord.status == ApprovalStatus.approved, 1), else_=0)).label("approved"),
                func.sum(case((ApprovalRecord.status == ApprovalStatus.pending, 1), else_=0)).label("pending"),
            )
            .join(User, ApprovalRecord.user_id == User.id)
            .filter(
                ApprovalRecord.is_deleted == False,
                User.department.isnot(None),
            )
            .group_by(User.department)
            .order_by(func.count(ApprovalRecord.id).desc())
            .limit(10)
            .all()
        )
        top_departments = [
            {"department": d or "未分配", "total": t, "approved": a or 0, "pending": p or 0}
            for d, t, a, p in dept_stats
        ]

    # ── 高频申请人 ──
    top_applicants = (
        db.query(
            User.username,
            func.count(ApprovalRecord.id).label("count"),
        )
        .join(User, ApprovalRecord.user_id == User.id)
        .filter(ApprovalRecord.is_deleted == False)
        .group_by(User.username)
        .order_by(func.count(ApprovalRecord.id).desc())
        .limit(5)
        .all()
    )
    top_applicants_list = [{"username": u, "count": c} for u, c in top_applicants]

    return {
        "total_users": total_users,
        "total_approvals": total_approvals,
        "pending_approvals": pending_approvals,
        "today_new_approvals": today_new,
        "approvals_by_day": daily_stats,
        "approvals_by_type": type_list,
        "approvals_by_status": status_stats,
        "avg_processing_hours": avg_hours,
        "approval_rate": approval_rate,
        "rejection_rate": rejection_rate,
        "top_departments": top_departments,
        "top_applicants": top_applicants_list,
    }
