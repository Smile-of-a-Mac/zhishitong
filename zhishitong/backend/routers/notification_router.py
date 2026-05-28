"""通知 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import SessionLocal
from auth import get_current_user
from models import User
from services.notification_service import (
    get_user_notifications, mark_as_read, mark_all_read,
)
from schemas import NotificationListOut, NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=NotificationListOut)
def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的通知列表"""
    result = get_user_notifications(db, current_user.id, page, page_size, unread_only)
    return NotificationListOut(
        items=[NotificationOut.model_validate(n) for n in result["items"]],
        total=result["total"],
        unread_count=result["unread_count"],
    )


@router.post("/{notification_id}/read")
def read_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记单条通知为已读"""
    ok = mark_as_read(db, notification_id, current_user.id)
    if not ok:
        raise HTTPException(404, "通知不存在或无权操作")
    return {"ok": True}


@router.post("/read-all")
def read_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全部标记已读"""
    count = mark_all_read(db, current_user.id)
    return {"ok": True, "count": count}


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取未读通知数量（用于红点角标）"""
    result = get_user_notifications(db, current_user.id, page=1, page_size=1)
    return {"unread_count": result["unread_count"]}
