"""公告 & 制度文库 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import SessionLocal
from auth import get_current_user
from models import User, Announcement
from schemas import AnnouncementCreate, AnnouncementOut

router = APIRouter(prefix="/api/announcements", tags=["announcements"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[AnnouncementOut])
def list_announcements(
    category: str = Query(None, pattern=r"^(announcement|policy|guide)$"),
    document_type: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """公告列表（所有登录用户可看）"""
    q = db.query(Announcement).filter(Announcement.is_published == True)
    if category:
        q = q.filter(Announcement.category == category)
    if document_type:
        q = q.filter(Announcement.document_type == document_type)

    items = q.order_by(
        Announcement.is_pinned.desc(),
        Announcement.created_at.desc(),
    ).limit(50).all()

    result = []
    for a in items:
        author_name = ""
        if a.author:
            author_name = a.author.real_name or a.author.username
        result.append(AnnouncementOut(
            id=a.id,
            title=a.title,
            content=a.content,
            category=a.category,
            document_type=a.document_type,
            is_pinned=a.is_pinned,
            is_published=a.is_published,
            author_name=author_name,
            view_count=a.view_count,
            created_at=a.created_at,
            updated_at=a.updated_at,
        ))
    return result


@router.get("/{announcement_id}", response_model=AnnouncementOut)
def get_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """公告详情（同时增加阅读量）"""
    a = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(404)
    a.view_count += 1
    db.commit()

    author_name = a.author.real_name or a.author.username if a.author else ""
    return AnnouncementOut(
        id=a.id,
        title=a.title,
        content=a.content,
        category=a.category,
        document_type=a.document_type,
        is_pinned=a.is_pinned,
        is_published=a.is_published,
        author_name=author_name,
        view_count=a.view_count,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


@router.post("", response_model=AnnouncementOut)
def create_announcement(
    data: AnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发布公告/制度（管理员）"""
    if not (current_user.is_admin or current_user.is_school_admin):
        raise HTTPException(403)

    a = Announcement(
        title=data.title,
        content=data.content,
        category=data.category,
        document_type=data.document_type,
        is_pinned=data.is_pinned,
        author_id=current_user.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return AnnouncementOut(
        id=a.id,
        title=a.title,
        content=a.content,
        category=a.category,
        document_type=a.document_type,
        is_pinned=a.is_pinned,
        is_published=a.is_published,
        author_name=current_user.real_name or current_user.username,
        view_count=0,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


@router.put("/{announcement_id}", response_model=AnnouncementOut)
def update_announcement(
    announcement_id: int,
    data: AnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑公告"""
    if not (current_user.is_admin or current_user.is_school_admin):
        raise HTTPException(403)
    a = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(404)
    for k, v in data.model_dump().items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return AnnouncementOut(
        id=a.id, title=a.title, content=a.content, category=a.category,
        document_type=a.document_type, is_pinned=a.is_pinned,
        is_published=a.is_published,
        author_name=current_user.real_name or current_user.username,
        view_count=a.view_count, created_at=a.created_at, updated_at=a.updated_at,
    )


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除公告"""
    if not (current_user.is_admin or current_user.is_school_admin):
        raise HTTPException(403)
    a = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(404)
    a.is_published = False
    db.commit()
    return {"ok": True}
