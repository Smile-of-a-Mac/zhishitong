"""
学校管理员路由 — 查看全校事务 / 学校级审批
"""
import json
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import User, ApprovalRecord, AdminAuditLog, ApprovalStatus
from schemas import DeptRecordOut, DeptRecordListOut, ApprovalStatusUpdate
from auth import require_school_admin
from services.logging_service import LogCategory, log
from services.workflow import get_stages, get_next_stage, get_stage_label
from services.notification_service import notify_review_result

router = APIRouter(prefix="/api/school", tags=["school"])


def _build_stages(record: ApprovalRecord) -> list[dict]:
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


@router.get("/affairs", response_model=DeptRecordListOut)
def list_school_affairs(
    document_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    admin: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    """学校管理员查看本校所有事务"""
    school = admin.school
    if admin.is_admin:
        q = db.query(ApprovalRecord).filter(ApprovalRecord.hard_deleted == False, ApprovalRecord.is_deleted == False)
    else:
        q = (
            db.query(ApprovalRecord)
            .join(User, ApprovalRecord.user_id == User.id)
            .filter(
                ApprovalRecord.hard_deleted == False,
                ApprovalRecord.is_deleted == False,
                User.school == school,  # 学校隔离
            )
        )

    if document_type:
        q = q.filter(ApprovalRecord.document_type == document_type)
    if status:
        q = q.filter(ApprovalRecord.status == ApprovalStatus(status))
    if stage:
        q = q.filter(ApprovalRecord.current_stage == stage)

    total = q.count()
    records = q.order_by(ApprovalRecord.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    items = [_record_to_out(r, db) for r in records]
    return DeptRecordListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/affairs/stats")
def school_affair_stats(
    admin: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    """全校事务统计"""
    school = admin.school
    if admin.is_admin:
        base = db.query(ApprovalRecord).filter(
            ApprovalRecord.hard_deleted == False,
            ApprovalRecord.is_deleted == False,
        )
    else:
        base = (
            db.query(ApprovalRecord)
            .join(User, ApprovalRecord.user_id == User.id)
            .filter(
                ApprovalRecord.hard_deleted == False,
                ApprovalRecord.is_deleted == False,
                User.school == school,  # 学校隔离
            )
        )
    total = base.count()
    pending = base.filter(ApprovalRecord.status == ApprovalStatus.pending).count()
    approved = base.filter(ApprovalRecord.status == ApprovalStatus.approved).count()
    rejected = base.filter(ApprovalRecord.status == ApprovalStatus.rejected).count()
    school_pending = base.filter(
        ApprovalRecord.current_stage == "school_review",
        ApprovalRecord.status == ApprovalStatus.pending,
    ).count()
    today = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today_new = base.filter(ApprovalRecord.created_at >= today).count()

    return {
        "total_records": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "school_pending": school_pending,
        "today_new": today_new,
    }


@router.get("/affairs/{record_id}", response_model=DeptRecordOut)
def get_school_affair(
    record_id: int,
    admin: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id, ApprovalRecord.hard_deleted == False,
    ).first()
    if not record:
        raise HTTPException(404, "事务不存在")
    # 学校隔离
    if not admin.is_admin:
        owner = db.query(User).filter(User.id == record.user_id).first()
        if not owner or owner.school != admin.school:
            raise HTTPException(403, "无权访问其他学校的事务")
    return _record_to_out(record, db)


@router.put("/records/{record_id}/status")
def update_school_status(
    record_id: int,
    body: ApprovalStatusUpdate,
    admin: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    """学校管理员审批：通过则完成，驳回则整单驳回"""
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id, ApprovalRecord.hard_deleted == False,
    ).with_for_update().first()
    if not record:
        raise HTTPException(404, "事务不存在")
    # 学校隔离
    if not admin.is_admin:
        owner = db.query(User).filter(User.id == record.user_id).first()
        if not owner or owner.school != admin.school:
            raise HTTPException(403, "无权审批其他学校的事务")
    if record.current_stage != "school_review":
        raise HTTPException(400, f"当前不在学校审批阶段（{record.current_stage}）")

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
        "stage": "school_review",
        "status": new_status,
        "reviewer": admin.username,
        "reason": reason,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    record.stage_history_json = json.dumps(stages, ensure_ascii=False)

    if new_status == "approved":
        record.status = ApprovalStatus.approved
        record.current_stage = "completed"
        if reason:
            record.decision_reason = f"[学校审批通过] {reason} — 全部审批完成"
        else:
            record.decision_reason = "[学校审批通过] 全部审批完成"
        notify_review_result(db, record_id, record.user_id, "通过", reason, _get_doc_label(record.document_type))
    else:
        record.status = ApprovalStatus(new_status)
        record.decision_reason = f"[学校管理员: {admin.username}] {reason}"
        notify_review_result(db, record_id, record.user_id, "驳回", reason, _get_doc_label(record.document_type))

    db.add(AdminAuditLog(
        admin_id=admin.id, action="school_review",
        target_type="approval_record", target_id=record_id,
        detail=f"学校审批: {old_status} → {new_status} | 理由: {reason or '（无）'}",
    ))
    db.commit()
    db.refresh(record)

    log(
        LogCategory.APPROVAL, "info",
        f"学校审批: record_id={record_id} → {new_status}",
        user_id=admin.id, record_id=record_id,
        old_status=old_status, new_status=new_status, reason=reason,
    )

    return {"detail": "学校审批完成", "record_id": record_id, "status": new_status, "reason": reason}
