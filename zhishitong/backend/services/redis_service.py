"""
Redis 服务层 — OCR 缓存 + 速率限制 + Key 池计数

连接: 优先 REDIS_URL 环境变量，默认 localhost:6379（db 0）
无 Redis 可用时所有功能静默降级，不影响主流程。
"""
import hashlib
import json
import logging
import os
from typing import Optional, Tuple

import redis.asyncio as aioredis
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
OCR_CACHE_TTL = int(os.getenv("OCR_CACHE_TTL", str(24 * 3600)))  # 24h
RATE_LIMIT_WINDOW = 60  # 1 分钟窗口
RATE_LIMIT_FREE = 10    # Free 层每分钟上限
RATE_LIMIT_PRO = 30     # Pro 层每分钟上限

_pool: Optional[Redis] = None
_available: Optional[bool] = None  # None=未检测, True=可用, False=不可用


async def _get_redis() -> Optional[Redis]:
    """懒连接 + 单例 Redis 客户端"""
    global _pool, _available
    if _available is False:
        return None
    if _pool is not None:
        return _pool
    try:
        _pool = aioredis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=3)
        await _pool.ping()
        _available = True
        logger.info(f"Redis 已连接: {REDIS_URL}")
        return _pool
    except Exception as e:
        _available = False
        _pool = None
        logger.warning(f"Redis 不可用 ({REDIS_URL}): {e}，相关功能已降级")
        return None


# ========== Phase 1: OCR 结果缓存 ==========

def _file_hash(image_bytes: bytes) -> str:
    """计算图片 SHA256 作为缓存 key"""
    return hashlib.sha256(image_bytes).hexdigest()


async def ocr_cache_get(image_bytes: bytes) -> Optional[dict]:
    """查 OCR 缓存，命中返回完整 OCRResult 字典（不含 bytes），未命中返回 None"""
    r = await _get_redis()
    if r is None:
        return None
    key = f"ocr:cache:{_file_hash(image_bytes)}"
    try:
        raw = await r.get(key)
        if raw:
            data = json.loads(raw)
            logger.info(f"OCR 缓存命中 (key={key[:16]}...)")
            return data
    except Exception as e:
        logger.warning(f"Redis GET 异常: {e}")
    return None


async def ocr_cache_set(image_bytes: bytes, result: dict, ttl: int = OCR_CACHE_TTL) -> None:
    """写入 OCR 缓存"""
    r = await _get_redis()
    if r is None:
        return
    key = f"ocr:cache:{_file_hash(image_bytes)}"
    try:
        await r.set(key, json.dumps(result, ensure_ascii=False, default=str), ex=ttl)
        logger.info(f"OCR 缓存写入 (key={key[:16]}..., ttl={ttl}s)")
    except Exception as e:
        logger.warning(f"Redis SET 异常: {e}")


# ========== Phase 2a: Key 池计数 ==========

async def keypool_incr_usage(key_id: int) -> None:
    """Redis INCR 记录 Key 使用次数（异步，不阻塞）"""
    import datetime as _dt
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.hincrby(f"apikey:{key_id}", "usage_count", 1)
        await r.hset(f"apikey:{key_id}", "last_used_ts",
                      _dt.datetime.now(_dt.timezone.utc).isoformat())
    except Exception:
        pass


async def keypool_incr_fail(key_id: int) -> None:
    """Redis INCR 记录 Key 失败次数，超阈值自动标记禁用"""
    r = await _get_redis()
    if r is None:
        return
    try:
        new_count = await r.hincrby(f"apikey:{key_id}", "fail_count", 1)
        if new_count >= 5:
            await r.hset(f"apikey:{key_id}", "disabled", "1")
            logger.warning(f"Key #{key_id} Redis 失败计数 {new_count} >= 5，标记禁用")
    except Exception:
        pass


async def keypool_get_stats(key_id: int) -> dict:
    """读取 Key 池统计（usage_count / fail_count）"""
    r = await _get_redis()
    if r is None:
        return {}
    try:
        return await r.hgetall(f"apikey:{key_id}")
    except Exception:
        return {}


# ========== Phase 2b: 速率限制 ==========

async def rate_limit_check(user_id: int, tier: str) -> Tuple[bool, int]:
    """
    检查 OCR 调用频率限制。
    返回 (allowed, remaining)。
    tier="free" → 10 次/分钟，tier="pro" → 30 次/分钟，tier="pro_plus" → 不限。
    """
    if tier == "pro_plus":
        return True, -1  # 不限

    limit = RATE_LIMIT_PRO if tier == "pro" else RATE_LIMIT_FREE
    r = await _get_redis()
    if r is None:
        return True, -1  # Redis 不可用时不限流（降级）

    key = f"rl:ocr:{user_id}"
    try:
        # 先写后读，避免 TOCTOU 竞态：INCR 是原子操作
        new_count = await r.incr(key)
        if new_count == 1:
            await r.expire(key, RATE_LIMIT_WINDOW)
        remaining = max(0, limit - new_count)
        if new_count > limit:
            return False, 0
        return True, remaining
    except Exception:
        return True, -1
