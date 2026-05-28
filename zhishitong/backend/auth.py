"""JWT 认证 + 用户依赖注入"""
import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from models import User
from database import get_db
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_DAYS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

UTC = datetime.timezone.utc


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
