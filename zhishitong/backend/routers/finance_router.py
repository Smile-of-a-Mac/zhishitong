"""
财务管理员路由 — 查看待财务审批的报销事务 / 审批
"""
import json, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database import get_db
from models import User, ApprovalRecord, AdminAuditLog, ApprovalStatus
from schemas import ApprovalStatusUpdate, DeptRecordOut, DeptRecordListOut, ApprovalStageInfo
from auth import require_finance_admin
from services.logging_service import LogCategory, log
from services.workflow import get_stages, get_next_stage, get_stage_label, get_stage_role
from services.notification_service import notify_review_result, notify_stage_advanced

router = APIRouter(prefix="/api/finance", tags=["finance"])


def _build_stage_list(record: ApprovalRecord) -> list[dict]:
    """从记录构建阶段列表"""
    try:
        stages = json.loads(record.stage_history_json or "[]")
    except (json.JSONDecodeError, TypeError):
        stages = []

    # 补充阶段中文标签
    for s in stages:
        s["label"] = get_stage_label(record.document_type, s.get("stage", ""))
    return stages


def _normalize_reason(reason: Optional[str]) -> str:
    return (reason or "").strip()


def _get_doc_label(doc_type: Optional[str]) -> str:
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
    owner = db.query(User).filter(User.id == record.user_id).first()
    stages = _build_stage_list(record)
    return DeptRecordOut(
        id=record.id,
        username=owner.username if owner else "unknown",
        department=owner.department if owner else None,
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


@router.get("/records", response_model=DeptRecordListOut)
def list_finance_records(
    status: Optional[str] = Query(None, pattern=r"^(pending|approved|rejected|needs_revision)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    """
    查看待财务审批的报销事务。
    财务管理员看到 current_stage=finance_review 的报销记录。
    """
    school = admin.school
    q = db.query(ApprovalRecord).join(User, ApprovalRecord.user_id == User.id).filter(
        ApprovalRecord.document_type == "reimbursement",
        ApprovalRecord.current_stage == "finance_review",
        ApprovalRecord.hard_deleted == False,
        ApprovalRecord.is_deleted == False,
        User.school == school,  # 学校隔离
    )

    if status:
        q = q.filter(ApprovalRecord.status == ApprovalStatus(status))

    total = q.count()
    records = q.order_by(ApprovalRecord.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    items = [_record_to_out(r, db) for r in records]
    return DeptRecordListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/stats")
def finance_stats(
    admin: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    """财务事务统计"""
    school = admin.school
    # base 统计全部报销记录（不限 current_stage），才能反映已处理的历史
    base = db.query(ApprovalRecord).join(User, ApprovalRecord.user_id == User.id).filter(
        ApprovalRecord.document_type == "reimbursement",
        ApprovalRecord.hard_deleted == False,
        ApprovalRecord.is_deleted == False,
        User.school == school,  # 学校隔离
    )
    total = base.count()
    # 待办：当前在财务审批阶段且状态 pending
    pending = base.filter(
        ApprovalRecord.current_stage == "finance_review",
        ApprovalRecord.status == ApprovalStatus.pending,
    ).count()
    approved = base.filter(ApprovalRecord.status == ApprovalStatus.approved).count()
    rejected = base.filter(ApprovalRecord.status == ApprovalStatus.rejected).count()
    today = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today_new = base.filter(ApprovalRecord.created_at >= today).count()

    return {
        "department": "财务处",
        "total_records": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "today_new": today_new,
    }


@router.get("/records/{record_id}", response_model=DeptRecordOut)
def get_finance_record(
    record_id: int,
    admin: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id,
        ApprovalRecord.hard_deleted == False,
    ).first()
    if not record:
        raise HTTPException(404, "事务记录不存在")
    # 学校隔离
    owner = db.query(User).filter(User.id == record.user_id).first()
    if not owner or owner.school != admin.school:
        raise HTTPException(403, "无权访问其他学校的事务")
    if record.document_type != "reimbursement":
        raise HTTPException(400, "非报销事务，无需财务审批")
    return _record_to_out(record, db)


@router.put("/records/{record_id}/status")
def update_finance_status(
    record_id: int,
    body: ApprovalStatusUpdate,
    admin: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    """财务管理员审批报销事务"""
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id,
        ApprovalRecord.hard_deleted == False,
    ).with_for_update().first()
    if not record:
        raise HTTPException(404, "事务记录不存在")
    if record.current_stage != "finance_review":
        raise HTTPException(400, f"当前不在财务审批阶段（当前阶段: {record.current_stage})")
    if record.document_type != "reimbursement":
        raise HTTPException(400, "非报销事务")

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
        "stage": "finance_review",
        "status": new_status,
        "reviewer": admin.username,
        "reason": reason,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    record.stage_history_json = json.dumps(stages, ensure_ascii=False)

    if new_status == "approved":
        # 财务审批通过 → 进入下一阶段或最终通过
        next_stage = get_next_stage(record.document_type, "finance_review", _parse_filled(record))
        if next_stage:
            next_label = get_stage_label(record.document_type, next_stage)
            record.current_stage = next_stage
            if reason:
                record.decision_reason = f"[财务审批通过] {reason} → 转交 {next_label}"
            else:
                record.decision_reason = f"[财务审批通过] 转交 {next_label}"
            notify_review_result(db, record_id, record.user_id, "通过", reason, _get_doc_label(record.document_type))
            notify_stage_advanced(db, record_id, record.user_id, next_label, _get_doc_label(record.document_type))
        else:
            record.status = ApprovalStatus.approved
            record.current_stage = "completed"
            if reason:
                record.decision_reason = f"[财务审批通过] {reason} — 全部审批完成"
            else:
                record.decision_reason = "[财务审批通过] 全部审批完成"
            notify_review_result(db, record_id, record.user_id, "通过", reason, _get_doc_label(record.document_type))
    else:
        record.status = ApprovalStatus(new_status)
        record.decision_reason = f"[财务管理员: {admin.username}] {reason}"
        notify_review_result(db, record_id, record.user_id, "驳回", reason, _get_doc_label(record.document_type))

    db.add(AdminAuditLog(
        admin_id=admin.id,
        action="finance_review",
        target_type="approval_record",
        target_id=record_id,
        detail=f"财务审批: {old_status} → {new_status} | 理由: {reason or '（无）'}",
    ))
    db.commit()
    db.refresh(record)

    log(
        LogCategory.APPROVAL, "info",
        f"财务审批: record_id={record_id} → {new_status}",
        user_id=admin.id, record_id=record_id,
        old_status=old_status, new_status=new_status,
        reason=reason,
    )

    return {"detail": "财务审批完成", "record_id": record_id, "status": new_status, "reason": reason}


def _parse_filled(record: ApprovalRecord) -> dict:
    try:
        return json.loads(record.filled_json) if record.filled_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}
