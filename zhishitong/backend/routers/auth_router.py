"""认证路由 — 注册 / 登录 / 个人信息"""
import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import User, TierEnum
from schemas import UserCreate, UserOut, Token, LoginRequest
from auth import hash_password, verify_password, create_token, get_current_user
from services.logging_service import LogCategory, log

router = APIRouter(prefix="/api", tags=["auth"])

# ---- 登录频率限制（滑动窗口，按 IP） ----
_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_LOGIN_LOCK = Lock()
_MAX_ATTEMPTS = 10        # 10 次失败
_WINDOW_SECONDS = 300     # 5 分钟窗口


def _check_login_rate(ip: str) -> None:
    now = time.time()
    with _LOGIN_LOCK:
        attempts = _LOGIN_ATTEMPTS[ip]
        attempts[:] = [t for t in attempts if now - t < _WINDOW_SECONDS]
        if len(attempts) >= _MAX_ATTEMPTS:
            raise HTTPException(429, f"登录尝试过于频繁，请 {_WINDOW_SECONDS // 60} 分钟后重试")
        attempts.append(now)


@router.post("/register", response_model=Token)
def register(body: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, "用户名已存在")

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        tier=TierEnum.free,
        llm_ocr_quota=0,
        llm_ocr_used=0,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log(LogCategory.AUTH, "info", f"新用户注册: {user.username}", user_id=user.id)
    return Token(access_token=create_token(user), user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # 频率限制
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate(client_ip)

    # 快速校验
    if not body.username.strip():
        raise HTTPException(400, "请输入用户名")
    if not body.password:
        raise HTTPException(400, "请输入密码")

    user = db.query(User).filter(User.username == body.username).first()
    if not user:
        log(LogCategory.AUTH, "warning", f"登录失败（用户不存在）: {body.username}", username=body.username)
        raise HTTPException(401, "用户名或密码错误，请检查后重试")
    if not verify_password(body.password, user.hashed_password):
        log(LogCategory.AUTH, "warning", f"登录失败（密码错误）: {body.username}", username=body.username)
        raise HTTPException(401, "用户名或密码错误，请检查后重试")
    if not user.is_active:
        log(LogCategory.AUTH, "warning", f"已禁用用户尝试登录: {user.username}", user_id=user.id)
        raise HTTPException(403, "该账号已被管理员禁用，请联系管理员恢复")
    log(LogCategory.AUTH, "info", f"用户登录: {user.username}", user_id=user.id, tier=user.tier.value)
    return Token(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


# ---- 修改密码 ----

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


@router.put("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """已登录用户修改自己的密码"""
    if not verify_password(body.old_password, user.hashed_password):
        raise HTTPException(400, "原密码错误")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    log(LogCategory.AUTH, "info", f"用户修改密码: {user.username}", user_id=user.id)
    return {"detail": "密码修改成功"}
