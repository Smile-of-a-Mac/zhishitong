"""
智能 API Key 池服务

策略（优先级从高到低）：
  1. 排除 fail_count >= 阈值的 Key（自动禁用）
  2. 优先选择 fail_count 最低的 Key
  3. fail_count 相同时，优先选 usage_count 较低 → 最后使用时间最久的（轮询均衡）
  
支持操作：
  - select_best: 按策略选取最优 Key
  - record_success: 使用成功，记录 usage_count++ & last_used_at
  - record_failure: 使用失败，fail_count++，超阈值自动禁用
"""
import asyncio
import datetime
import logging
from typing import Optional, NamedTuple

from sqlalchemy.orm import Session

from models import ApiKey, ApiKeyType
from services.crypto_service import decrypt
from services.redis_service import keypool_incr_usage, keypool_incr_fail

logger = logging.getLogger(__name__)

# 自动禁用阈值
FAIL_THRESHOLD = 5


class ResolvedKey(NamedTuple):
    """解析后的 Key 配置"""
    key_id: Optional[int]       # 数据库中的 Key ID（None 表示环境变量）
    api_base: str
    api_key: str
    model: str


def select_best(db: Session, key_type: ApiKeyType) -> Optional[ApiKey]:
    """
    从池中选取最优 Key。
    策略：fail_count 最低 → usage_count 最低 → 最久未使用
    排除已禁用的 Key。
    """
    candidates = (
        db.query(ApiKey)
        .filter(
            ApiKey.key_type == key_type,
            ApiKey.is_active == True,
            ApiKey.fail_count < FAIL_THRESHOLD,
        )
        .order_by(
            ApiKey.fail_count.asc(),
            ApiKey.usage_count.asc(),
            ApiKey.last_used_at.asc().nullsfirst(),
        )
        .all()
    )
    return candidates[0] if candidates else None


def resolve_key(
    db: Session,
    key_type: ApiKeyType,
    fallback_base: str,
    fallback_key: str,
    fallback_model: str,
) -> ResolvedKey:
    """
    从 Key 池或环境变量解析密钥。
    返回 ResolvedKey(key_id, api_base, api_key, model)。
    key_id 为 None 表示使用的是环境变量（无数据库记录，无法追踪用量）。
    """
    candidates = (
        db.query(ApiKey)
        .filter(
            ApiKey.key_type == key_type,
            ApiKey.is_active == True,
            ApiKey.fail_count < FAIL_THRESHOLD,
        )
        .order_by(
            ApiKey.fail_count.asc(),
            ApiKey.usage_count.asc(),
            ApiKey.last_used_at.asc().nullsfirst(),
        )
        .all()
    )
    for best in candidates:
        try:
            decrypted = decrypt(best.api_key_encrypted)
            return ResolvedKey(
                key_id=best.id,
                api_base=best.api_base,
                api_key=decrypted,
                model=best.default_model,
            )
        except Exception as e:
            logger.warning(f"Key 池 #{best.id} 解密失败: {e}")
            # 解密失败也算一次失败
            record_failure(db, best.id)
            continue

    # 回退到环境变量
    return ResolvedKey(key_id=None, api_base=fallback_base, api_key=fallback_key, model=fallback_model)


async def _redis_incr_usage(key_id: int):
    """异步写入 Redis 计数（不阻塞主流程）"""
    try:
        await keypool_incr_usage(key_id)
    except Exception:
        pass


def record_success(db: Session, key_id: Optional[int]) -> None:
    """记录一次成功使用"""
    if key_id is None:
        return  # 环境变量 Key，无法追踪
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if key:
        key.usage_count = (key.usage_count or 0) + 1
        key.last_used_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
    # 异步写入 Redis（不阻塞）
    try:
        asyncio.get_running_loop().create_task(_redis_incr_usage(key_id))
    except RuntimeError:
        pass


async def _redis_incr_fail(key_id: int):
    """异步写入 Redis 失败计数"""
    try:
        await keypool_incr_fail(key_id)
    except Exception:
        pass


def record_failure(db: Session, key_id: Optional[int]) -> None:
    """记录一次失败，超阈值自动禁用"""
    if key_id is None:
        return
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if key:
        key.fail_count = (key.fail_count or 0) + 1
        key.last_used_at = datetime.datetime.now(datetime.timezone.utc)
        if key.fail_count >= FAIL_THRESHOLD:
            key.is_active = False
            logger.warning(
                f"Key 池 #{key_id} ({key.provider}/{key.default_model}) "
                f"失败次数 {key.fail_count} >= {FAIL_THRESHOLD}，已自动禁用"
            )
        db.commit()
    # 异步写入 Redis 失败计数（不阻塞）
    try:
        asyncio.get_running_loop().create_task(_redis_incr_fail(key_id))
    except RuntimeError:
        pass


def get_pool_stats(db: Session, key_type: ApiKeyType) -> dict:
    """获取指定类型 Key 池的统计信息"""
    total = db.query(ApiKey).filter(ApiKey.key_type == key_type).count()
    active = db.query(ApiKey).filter(
        ApiKey.key_type == key_type, ApiKey.is_active == True
    ).count()
    disabled = db.query(ApiKey).filter(
        ApiKey.key_type == key_type, ApiKey.is_active == False
    ).count()
    total_usage = db.query(ApiKey).filter(ApiKey.key_type == key_type).with_entities(
        ApiKey.usage_count
    ).all()
    total_usage_sum = sum(row[0] or 0 for row in total_usage)
    return {
        "key_type": key_type.value,
        "total": total,
        "active": active,
        "disabled": disabled,
        "total_usage": total_usage_sum,
        "fail_threshold": FAIL_THRESHOLD,
    }
