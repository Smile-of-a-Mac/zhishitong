"""
路由共享辅助 — dept_router / finance_router / approval_router 复用
"""
import json
from typing import Optional

from sqlalchemy.orm import Session

from models import User, ApprovalRecord
from schemas import DeptRecordOut
from services.workflow import get_stage_label
from constants import get_doc_label


def build_stages(record: ApprovalRecord) -> list[dict]:
    """从记录构建阶段列表，补充中文标签"""
    try:
        stages = json.loads(record.stage_history_json or "[]")
    except (json.JSONDecodeError, TypeError):
        stages = []
    for s in stages:
        s["label"] = s.get("label") or get_stage_label(record.document_type, s.get("stage", ""))
    return stages


def parse_filled(record: ApprovalRecord) -> dict:
    """安全解析 filled_json"""
    try:
        return json.loads(record.filled_json) if record.filled_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def normalize_reason(reason: Optional[str]) -> str:
    return (reason or "").strip()


def record_to_out(record: ApprovalRecord, db: Session) -> DeptRecordOut:
    """将 ApprovalRecord 转为 DeptRecordOut 响应模型"""
    owner = db.query(User).filter(User.id == record.user_id).first()
    stages = build_stages(record)
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
