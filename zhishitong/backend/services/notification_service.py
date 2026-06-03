"""站内信通知服务 — 创建、查询、标记已读"""
import json, datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from models import Notification, NotificationType


def create_notification(
    db: Session,
    user_id: int,
    ntype: NotificationType,
    title: str,
    body: str,
    record_id: Optional[int] = None,
) -> Notification:
    """创建一条站内信通知"""
    notif = Notification(
        user_id=user_id,
        type=ntype,
        title=title,
        body=body,
        record_id=record_id,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def get_user_notifications(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
    types: Optional[List[str]] = None,
) -> dict:
    """获取用户通知列表，返回 items + total + unread_count"""
    q = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    if types:
        q = q.filter(Notification.type.in_(types))

    total = q.count()
    unread_count = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .count()
    )

    items = (
        q.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": items, "total": total, "unread_count": unread_count}


def mark_as_read(db: Session, notification_id: int, user_id: int) -> bool:
    """标记单条通知为已读"""
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not notif:
        return False
    notif.is_read = True
    db.commit()
    return True


def mark_all_read(db: Session, user_id: int) -> int:
    """标记所有通知为已读，返回更新条数"""
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .update({"is_read": True})
    )
    db.commit()
    return count


def delete_old_notifications(db: Session, days: int = 90) -> int:
    """清理超过 N 天的已读通知"""
    cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
    count = (
        db.query(Notification)
        .filter(Notification.is_read == True, Notification.created_at < cutoff)
        .delete()
    )
    db.commit()
    return count


# ── 便捷方法：审批各环节自动发通知 ──

def notify_submitted(db: Session, record_id: int, applicant_id: int, applicant_name: str,
                     doc_type_label: str, dept_admin_ids: List[int]):
    """申请提交后通知部门管理员"""
    for uid in dept_admin_ids:
        create_notification(
            db, uid,
            NotificationType.approval_submitted,
            "📋 新的审批申请",
            f"{applicant_name} 提交了「{doc_type_label}」申请，请及时处理",
            record_id=record_id,
        )


def notify_review_result(db: Session, record_id: int, applicant_id: int,
                         status_label: str, reason: str, doc_type_label: str):
    """审批结果通知申请人"""
    emoji_map = {
        "通过": "✅", "驳回": "❌", "需修改": "⚠️",
    }
    emoji = emoji_map.get(status_label, "📌")
    ntype_map = {
        "通过": NotificationType.approval_approved,
        "驳回": NotificationType.approval_rejected,
        "需修改": NotificationType.approval_needs_revision,
    }
    create_notification(
        db, applicant_id,
        ntype_map.get(status_label, NotificationType.approval_rejected),
        f"{emoji} 审批{status_label}",
        f"你的「{doc_type_label}」申请已被{status_label}。理由：{reason[:100]}",
        record_id=record_id,
    )


def notify_stage_advanced(db: Session, record_id: int, applicant_id: int,
                          stage_label: str, doc_type_label: str):
    """审批进入下一阶段时通知申请人"""
    create_notification(
        db, applicant_id,
        NotificationType.stage_advanced,
        "🔄 审批阶段变更",
        f"你的「{doc_type_label}」申请已进入「{stage_label}」阶段",
        record_id=record_id,
    )


def notify_urged(db: Session, record_id: int, dept_admin_ids: List[int],
                 applicant_name: str, doc_type_label: str):
    """催办通知审批人"""
    for uid in dept_admin_ids:
        create_notification(
            db, uid,
            NotificationType.approval_urged,
            "⏰ 催办提醒",
            f"{applicant_name} 催办了「{doc_type_label}」申请，请尽快处理",
            record_id=record_id,
        )
