"""认证路由 — 注册 / 登录 / 个人信息"""
import time
from collections import defaultdict
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import User, TierEnum
from schemas import UserCreate, UserOut, Token, LoginRequest
from auth import hash_password, verify_password, create_token, create_access_token, create_refresh_token, get_current_user
from auth import clear_test_override
from services.logging_service import LogCategory, log
from config import APP_ENV

router = APIRouter(prefix="/api", tags=["auth"])


def _cookie_secure(request: Request) -> bool:
    """仅在 HTTPS 或生产环境下启用 Secure Cookie。
    HTTP 本地开发环境下设 False，否则浏览器拒绝存储 secure cookie。"""
    if APP_ENV == "production":
        return True
    # 也检查实际请求协议：通过代理时可能用 X-Forwarded-Proto
    proto = request.headers.get("X-Forwarded-Proto", "")
    if proto == "https":
        return True
    return request.url.scheme == "https"

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
def register(body: UserCreate, request: Request, response: Response, db: Session = Depends(get_db)):
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

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    secure = _cookie_secure(request)
    response.set_cookie(
        key="auth_token",
        value=access_token,
        httponly=True, secure=secure, samesite="strict",
        max_age=30 * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True, secure=secure, samesite="strict",
        max_age=7 * 24 * 3600,
        path="/api/auth/refresh",
    )
    return Token(access_token=access_token, refresh_token=refresh_token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
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
    # 管理员登录时自动清除测试模拟覆盖
    if user.is_admin:
        clear_test_override(user.id)

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    # 设置 HttpOnly; SameSite=Strict Cookie（secure 根据环境自适应）
    secure = _cookie_secure(request)
    response.set_cookie(
        key="auth_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=30 * 60,  # 30 分钟
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=7 * 24 * 3600,
        path="/api/auth/refresh",  # 仅 refresh 端点可见
    )
    return Token(access_token=access_token, refresh_token=refresh_token, user=UserOut.model_validate(user))


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


# ---- Token 刷新 ----

from auth import verify_refresh_token, create_access_token

class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None  # 可传入或从 Cookie 读取


@router.post("/auth/refresh", response_model=Token)
def refresh_token(
    request: Request,
    response: Response,
    body: RefreshRequest = RefreshRequest(),
    db: Session = Depends(get_db),
):
    """使用 Refresh Token 换取新的 Access Token"""
    refresh_token_str = body.refresh_token or request.cookies.get("refresh_token")
    if not refresh_token_str:
        raise HTTPException(401, "缺少 Refresh Token")

    user_id = verify_refresh_token(refresh_token_str)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(401, "用户不存在或未激活")

    access_token = create_access_token(user)
    secure = _cookie_secure(request)
    response.set_cookie(
        key="auth_token",
        value=access_token,
        httponly=True, secure=secure, samesite="strict",
        max_age=30 * 60,
    )
    return Token(access_token=access_token, user=UserOut.model_validate(user))


# ---- 登出 ----

@router.post("/auth/logout")
def logout(response: Response):
    """清除认证 Cookie"""
    response.delete_cookie(key="auth_token")
    response.delete_cookie(key="refresh_token", path="/api/auth/refresh")
    return {"detail": "已登出"}
