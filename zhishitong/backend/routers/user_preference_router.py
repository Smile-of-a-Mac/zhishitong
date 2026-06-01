"""用户偏好 API — 申请模板收藏等个人设置"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User, UserPreference
from schemas import FavoriteApplyPathsIn, FavoriteApplyPathsOut

router = APIRouter(prefix="/api/user/preferences", tags=["user-preferences"])

ALLOWED_FAVORITE_PATHS = {
    "/apply/reimbursement",
    "/apply/leave",
    "/apply/club_application",
    "/apply/scholarship",
    "/apply/suspend_resume",
    "/apply/enrollment_proof",
    "/apply/diploma_verification",
    "/apply/transcript_print",
    "/apply/class_reschedule",
    "/apply/makeup_exam",
    "/apply/exam_review",
    "/apply/classroom_booking",
    "/apply/dorm_change",
    "/apply/seal_application",
}


def _clean_favorites(paths: list[str]) -> list[str]:
    cleaned: list[str] = []
    for path in paths:
        if path in ALLOWED_FAVORITE_PATHS and path not in cleaned:
            cleaned.append(path)
    return cleaned[:20]


def _get_or_create_preferences(db: Session, user_id: int) -> UserPreference:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if pref:
        return pref
    pref = UserPreference(user_id=user_id, favorite_apply_paths="[]")
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


@router.get("/favorites", response_model=FavoriteApplyPathsOut)
def get_favorites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pref = _get_or_create_preferences(db, user.id)
    try:
        favorites = json.loads(pref.favorite_apply_paths or "[]")
    except (json.JSONDecodeError, TypeError):
        favorites = []
    return FavoriteApplyPathsOut(favorites=_clean_favorites(favorites))


@router.put("/favorites", response_model=FavoriteApplyPathsOut)
def update_favorites(
    body: FavoriteApplyPathsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pref = _get_or_create_preferences(db, user.id)
    favorites = _clean_favorites(body.favorites)
    pref.favorite_apply_paths = json.dumps(favorites, ensure_ascii=False)
    db.commit()
    return FavoriteApplyPathsOut(favorites=favorites)
