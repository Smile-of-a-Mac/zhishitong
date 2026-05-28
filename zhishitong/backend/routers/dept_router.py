"""
部门管理员路由 — 查看本部门事务 / 多阶段审批
"""
import json
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import User, ApprovalRecord, AdminAuditLog, ApprovalStatus
from schemas import (
    ApprovalStatusUpdate, DeptRecordOut, DeptRecordListOut, DeptStatsOut,
)
from auth import require_dept_admin
from services.logging_service import LogCategory, log
from services.workflow import get_stages, get_next_stage, get_stage_label, get_stage_role
from services.notification_service import notify_review_result, notify_stage_advanced

router = APIRouter(prefix="/api/dept", tags=["department"])


def _build_stages(record: ApprovalRecord) -> list[dict]:
    """从记录构建阶段列表"""
    try:
        stages = json.loads(record.stage_history_json or "[]")
    except (json.JSONDecodeError, TypeError):
        stages = []
    for s in stages:
        s["label"] = s.get("label", get_stage_label(record.document_type, s.get("stage", "")))
    return stages


def _parse_filled(record: ApprovalRecord) -> dict:
    try:
        return json.loads(record.filled_json) if record.filled_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _normalize_reason(reason: Optional[str]) -> str:
    return (reason or "").strip()


def _get_doc_label(doc_type: Optional[str]) -> str:
    """文档类型 → 中文标签，用于通知消息"""
    if not doc_type:
        return "未知事务"
    return {
        "reimbursement": "报销申请", "leave": "请假申请", 
        "club_application": "社团活动申请", "classroom_booking": "教室借用",
        "business_trip": "出差申请", "seal_application": "用章申请",
        "dorm_change": "宿舍调换", "scholarship": "奖学金申请",
        "suspend_resume": "休学/复学", "enrollment_proof": "在读证明",
        "abroad_application": "因公出国", "onboarding": "入职报到",
        "office_supplies": "办公用品领用", "book_purchase": "图书采购",
    }.get(doc_type, doc_type)


def _record_to_out(record: ApprovalRecord, db: Session) -> DeptRecordOut:
    u = db.query(User).filter(User.id == record.user_id).first()
    stages = _build_stages(record)
    return DeptRecordOut(
        id=record.id,
        username=u.username if u else "unknown",
        department=u.department if u else None,
        original_filename=record.original_filename,
        document_type=record.document_type,
        status=record.status.value if record.status else "pending",
        current_stage=record.current_stage or "dept_review",
        filled_json=record.filled_json,
        decision_reason=record.decision_reason,
        suggestions=record.suggestions,
        missing_info=record.missing_info,
        stages=stages,
        image_url=f"/api/files/{record.id}" if record.storage_path and record.storage_path != "manual" else None,
        is_deleted=record.is_deleted,
        created_at=record.created_at,
    )


# ========== 事务列表 ==========

@router.get("/records", response_model=DeptRecordListOut)
def list_dept_records(
    status: Optional[str] = Query(None, pattern=r"^(pending|approved|rejected|needs_revision)$"),
    username: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_dept_admin),
    db: Session = Depends(get_db),
):
    """
    查看本部门所有事务。
    """
    dept = admin.department
    school = admin.school
    if admin.is_admin:
        q = db.query(ApprovalRecord).join(User, ApprovalRecord.user_id == User.id)
    else:
        q = (
            db.query(ApprovalRecord)
            .join(User, ApprovalRecord.user_id == User.id)
            .filter(
                User.department == dept,
                User.school == school,  # 学校隔离
            )
        )

    q = q.filter(
        ApprovalRecord.hard_deleted == False,
        ApprovalRecord.is_deleted == False,
        ApprovalRecord.status != ApprovalStatus.withdrawn,  # 撤回的申请部门管理员不可见
    )

    # 可选的阶段过滤（默认不过滤，这样管理员可以看到所有阶段的记录）
    if stage:
        q = q.filter(ApprovalRecord.current_stage == stage)

    if status:
        q = q.filter(ApprovalRecord.status == ApprovalStatus(status))

    if username:
        uids = [u.id for u in db.query(User).filter(User.username.contains(username)).all()]
        if uids:
            q = q.filter(ApprovalRecord.user_id.in_(uids))
        else:
            return DeptRecordListOut(items=[], total=0, page=page, page_size=page_size)

    total = q.count()
    records = q.order_by(ApprovalRecord.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    items = [_record_to_out(r, db) for r in records]
    return DeptRecordListOut(items=items, total=total, page=page, page_size=page_size)


# ========== 更改审批状态 ==========

@router.put("/records/{record_id}/status")
def update_record_status(
    record_id: int,
    body: ApprovalStatusUpdate,
    admin: User = Depends(require_dept_admin),
    db: Session = Depends(get_db),
):
    """
    部门管理员审批：通过则流转到下一阶段，驳回则整单驳回。
    """
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id, ApprovalRecord.hard_deleted == False,
    ).with_for_update().first()
    if not record:
        raise HTTPException(404, "事务记录不存在")

    if not admin.is_admin:
        owner = db.query(User).filter(User.id == record.user_id).first()
        if not owner or owner.department != admin.department or owner.school != admin.school:
            raise HTTPException(403, "无权审批其他部门的事务")
    if record.current_stage != "dept_review":
        raise HTTPException(400, f"当前不在部门审批阶段（{record.current_stage}）")

    old_status = record.status.value if record.status else "pending"
    new_status = body.status
    reason = _normalize_reason(body.reason)

    if new_status in {"rejected", "needs_revision"} and not reason:
        raise HTTPException(400, "驳回或需修改时必须填写审批理由")

    # 记录阶段历史
    try:
        stages = json.loads(record.stage_history_json or "[]")
    except (json.JSONDecodeError, TypeError):
        stages = []
    stages.append({
        "stage": "dept_review",
        "status": new_status,
        "reviewer": admin.username,
        "reason": reason,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    record.stage_history_json = json.dumps(stages, ensure_ascii=False)

    if new_status == "approved":
        # 部门审批通过 → 进入下一阶段
        filled = _parse_filled(record)
        next_stage = get_next_stage(record.document_type, "dept_review", filled)
        if next_stage:
            next_label = get_stage_label(record.document_type, next_stage)
            record.current_stage = next_stage
            if reason:
                record.decision_reason = f"[部门审批通过] {reason} → 转交 {next_label}"
            else:
                record.decision_reason = f"[部门审批通过] 转交 {next_label}"
            # 通知申请人：审批通过，进入下一阶段
            notify_review_result(db, record_id, record.user_id, "通过", reason, _get_doc_label(record.document_type))
            notify_stage_advanced(db, record_id, record.user_id, next_label, _get_doc_label(record.document_type))
        else:
            record.status = ApprovalStatus.approved
            record.current_stage = "completed"
            if reason:
                record.decision_reason = f"[部门审批通过] {reason} — 全部审批完成"
            else:
                record.decision_reason = "[部门审批通过] 全部审批完成"
            # 通知申请人：最终通过
            notify_review_result(db, record_id, record.user_id, "通过", reason, _get_doc_label(record.document_type))
    elif new_status == "needs_revision":
        record.status = ApprovalStatus.needs_revision
        record.decision_reason = f"[部门标记需修改] {reason}"
        # 通知申请人：需修改
        notify_review_result(db, record_id, record.user_id, "需修改", reason, _get_doc_label(record.document_type))
    else:
        record.status = ApprovalStatus(new_status)
        record.decision_reason = f"[部门管理员: {admin.username}] {reason}"
        # 通知申请人：驳回
        notify_review_result(db, record_id, record.user_id, "驳回", reason, _get_doc_label(record.document_type))

    db.add(AdminAuditLog(
        admin_id=admin.id, action="dept_review",
        target_type="approval_record", target_id=record_id,
        detail=f"{old_status} → {new_status} | 理由: {reason or '（无）'}",
    ))
    db.commit()
    db.refresh(record)

    log(
        LogCategory.APPROVAL, "info",
        f"部门审批: record_id={record_id} → {new_status}",
        user_id=admin.id, record_id=record_id,
        department=admin.department, old_status=old_status,
        new_status=new_status, reason=reason,
    )

    return {"detail": "部门审批完成", "record_id": record_id, "status": new_status, "reason": reason}


# ========== 统计 ==========

@router.get("/stats", response_model=DeptStatsOut)
def dept_stats(
    admin: User = Depends(require_dept_admin),
    db: Session = Depends(get_db),
):
    """本部门事务统计"""
    dept = admin.department
    school = admin.school

    if admin.is_admin:
        base = db.query(ApprovalRecord).filter(ApprovalRecord.hard_deleted == False)
    else:
        base = (
            db.query(ApprovalRecord)
            .join(User, ApprovalRecord.user_id == User.id)
            .filter(
                User.department == dept,
                User.school == school,
                ApprovalRecord.hard_deleted == False,
            )
        )

    total = base.count()
    pending = base.filter(ApprovalRecord.status == ApprovalStatus.pending).count()
    approved = base.filter(ApprovalRecord.status == ApprovalStatus.approved).count()
    rejected = base.filter(ApprovalRecord.status == ApprovalStatus.rejected).count()
    today = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today_new = base.filter(ApprovalRecord.created_at >= today).count()

    return DeptStatsOut(
        department=dept or "全部",
        total_records=total,
        pending=pending,
        approved=approved,
        rejected=rejected,
        today_new=today_new,
    )


# ========== 查看单条详情 ==========

@router.get("/records/{record_id}", response_model=DeptRecordOut)
def get_dept_record(
    record_id: int,
    admin: User = Depends(require_dept_admin),
    db: Session = Depends(get_db),
):
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id, ApprovalRecord.hard_deleted == False,
    ).first()
    if not record:
        raise HTTPException(404, "事务记录不存在")
    if not admin.is_admin:
        owner = db.query(User).filter(User.id == record.user_id).first()
        if not owner or owner.department != admin.department:
            raise HTTPException(403, "无权查看")
    return _record_to_out(record, db)
