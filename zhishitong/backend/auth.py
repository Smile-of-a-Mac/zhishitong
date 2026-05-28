"""JWT 认证 + 用户依赖注入 + 管理员测试模拟"""
import datetime
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from models import User, TierEnum
from database import get_db
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_DAYS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

UTC = datetime.timezone.utc

# ===== 管理员测试模拟：在内存中临时覆盖角色/订阅/学校 =====
# key: admin_user_id, value: 覆盖字段 dict
_test_overrides: dict[int, dict] = {}


def set_test_override(admin_id: int, overrides: dict):
    """设置测试覆盖（仅管理员可用）"""
    _test_overrides[admin_id] = overrides


def clear_test_override(admin_id: int):
    """清除测试覆盖"""
    _test_overrides.pop(admin_id, None)


def get_test_override(admin_id: int) -> Optional[dict]:
    """获取当前测试覆盖"""
    return _test_overrides.get(admin_id)


def _apply_overrides(user: User, overrides: dict):
    """将覆盖字段应用到 User 对象（不写库）"""
    if "tier" in overrides:
        try:
            user.tier = TierEnum(overrides["tier"])
        except ValueError:
            pass
    for field in ("is_dept_admin", "is_school_admin", "is_finance_admin", "is_admin"):
        if field in overrides:
            setattr(user, field, bool(overrides[field]))
    if "department" in overrides:
        user.department = overrides["department"] or ""
    if "school" in overrides:
        user.school = overrides["school"] or ""


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "tier": user.tier.value,
        "is_admin": user.is_admin,
        "is_school_admin": user.is_school_admin,
        "is_dept_admin": user.is_dept_admin,
        "is_finance_admin": user.is_finance_admin,
        "department": user.department or "",
        "school": user.school or "",
        "exp": datetime.datetime.now(UTC) + datetime.timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="无效的 Token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或未激活")

    # ── 管理员测试模拟：应用临时覆盖（expunge 防止误写库）──
    if user.is_admin and user_id in _test_overrides:
        _apply_overrides(user, _test_overrides[user_id])
        db.expunge(user)  # 关键：从会话分离，后续 commit 不会持久化模拟修改

    return user


async def get_raw_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """获取用户原始身份（不应用测试模拟覆盖），供测试面板自检使用"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="无效的 Token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或未激活")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def require_school_admin(user: User = Depends(get_current_user)) -> User:
    """需要学校管理员或超级管理员权限"""
    if not user.is_school_admin and not user.is_admin:
        raise HTTPException(status_code=403, detail="需要学校管理员权限")
    return user


async def require_dept_admin(user: User = Depends(get_current_user)) -> User:
    """部门管理员或超级管理员可访问部门事务"""
    if not user.is_dept_admin and not user.is_admin:
        raise HTTPException(status_code=403, detail="需要部门管理员权限")
    if not user.is_admin and not user.department:
        raise HTTPException(status_code=400, detail="当前账号未设置所属部门，请联系学校管理员")
    return user


async def require_finance_admin(user: User = Depends(get_current_user)) -> User:
    """需要财务管理员权限"""
    if not user.is_finance_admin:
        raise HTTPException(status_code=403, detail="需要财务管理员权限")
    return user
