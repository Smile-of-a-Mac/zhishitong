"""
结构化日志服务 — JSON 格式，分级分类，持久化到 DB

使用方式:
    from services.logging_service import LogCategory, log

    log(LogCategory.OCR, "info", "OCR 完成", user_id=1, provider="easyocr", duration_ms=320)
    log(LogCategory.SYSTEM, "error", "推理服务不可达", detail="Connection refused")
"""
import datetime, json, logging, sys, traceback
from enum import Enum
from typing import Optional, Any

logger = logging.getLogger("zhishitong.system")


class LogCategory(str, Enum):
    AUTH = "auth"           # 登录/注册/鉴权
    OCR = "ocr"             # 图片识别
    APPROVAL = "approval"   # 审批流程
    ADMIN = "admin"         # 管理员操作
    SYSTEM = "system"       # 系统级（启动/关闭/健康检查）
    INFERENCE = "inference" # 本地推理服务


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ===== 内存缓冲区（用于实时查询，避免频繁 DB 读） =====
_BUFFER: list[dict] = []
_BUFFER_MAX = 500  # 保留最近 500 条


def _format_extra(extra: dict) -> dict:
    """确保 extra 中的值可 JSON 序列化"""
    result = {}
    for k, v in extra.items():
        if isinstance(v, (datetime.datetime,)):
            result[k] = v.isoformat()
        elif isinstance(v, (Exception,)):
            result[k] = f"{type(v).__name__}: {v}"
        else:
            try:
                json.dumps(v)
                result[k] = v
            except (TypeError, ValueError):
                result[k] = str(v)
    return result


def log(
    category: LogCategory,
    level: str,
    message: str,
    user_id: Optional[int] = None,
    record_id: Optional[int] = None,
    duration_ms: Optional[float] = None,
    error_trace: Optional[str] = None,
    **extra,
):
    """统一日志入口 — 同时输出到控制台、文件、内存缓冲、DB"""
    entry = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "category": category.value if isinstance(category, LogCategory) else category,
        "level": level,
        "message": message,
        "user_id": user_id,
        "record_id": record_id,
        "duration_ms": duration_ms,
        "error_trace": error_trace,
        "extra": _format_extra(extra) if extra else {},
    }

    # 1. 控制台输出（给 docker logs / uvicorn 看）
    extras_str = ""
    if extra:
        extras_str = " | " + " ".join(f"{k}={v}" for k, v in _format_extra(extra).items())
    console_msg = f"[{entry['category'].upper()}] [{level.upper()}] {message}{extras_str}"
    if error_trace:
        console_msg += f"\n{error_trace}"

    if level in ("error", "critical"):
        logger.error(console_msg)
    elif level == "warning":
        logger.warning(console_msg)
    else:
        logger.info(console_msg)

    # 2. 内存缓冲
    _BUFFER.append(entry)
    if len(_BUFFER) > _BUFFER_MAX:
        _BUFFER[:] = _BUFFER[-_BUFFER_MAX:]

    # 3. DB 持久化（异步写入，不阻塞请求）
    _persist_to_db(entry)


def log_error(
    category: LogCategory,
    message: str,
    exc: Optional[Exception] = None,
    **extra,
):
    """便捷方法：记录异常"""
    trace = None
    if exc:
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log(category, "error", message, error_trace=trace, **extra)


# ===== DB 持久化（延迟导入避免循环依赖） =====
_db_session = None


def _get_db():
    global _db_session
    if _db_session is None:
        from database import SessionLocal
        _db_session = SessionLocal
    return _db_session()


def _persist_to_db(entry: dict):
    """将日志写入 DB（尽力而为，不抛异常）"""
    try:
        from models import SystemLog as SystemLogModel
        db = _get_db()
        sl = SystemLogModel(
            category=entry["category"],
            level=entry["level"],
            message=entry["message"][:512],
            user_id=entry.get("user_id"),
            record_id=entry.get("record_id"),
            duration_ms=entry.get("duration_ms"),
            error_trace=entry.get("error_trace", "")[:4096] if entry.get("error_trace") else "",
            extra_json=json.dumps(entry.get("extra", {}), ensure_ascii=False)[:2048],
        )
        db.add(sl)
        db.commit()
        db.close()
    except Exception:
        pass  # 日志写入失败不应影响主流程


# ===== 查询接口 =====

def get_recent_logs(
    category: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 100,
    from_db: bool = False,
) -> list[dict]:
    """获取最近日志"""
    if from_db:
        try:
            db = _get_db()
            from models import SystemLog as SystemLogModel
            q = db.query(SystemLogModel)
            if category:
                q = q.filter(SystemLogModel.category == category)
            if level:
                q = q.filter(SystemLogModel.level == level)
            rows = q.order_by(SystemLogModel.created_at.desc()).limit(limit).all()
            db.close()
            return [_row_to_dict(r) for r in rows]
        except Exception:
            pass

    # 从内存缓冲返回
    result = _BUFFER
    if category:
        result = [e for e in result if e["category"] == category]
    if level:
        result = [e for e in result if e["level"] == level]
    return list(reversed(result[-limit:]))


def _row_to_dict(row) -> dict:
    ts = row.created_at
    if ts:
        # 数据库存的是 naive UTC，转为本地时间输出
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc).astimezone()
        ts_str = ts.isoformat()
    else:
        ts_str = ""
    return {
        "id": row.id,
        "timestamp": ts_str,
        "category": row.category,
        "level": row.level,
        "message": row.message,
        "user_id": row.user_id,
        "record_id": row.record_id,
        "duration_ms": row.duration_ms,
        "error_trace": row.error_trace,
        "extra": json.loads(row.extra_json) if row.extra_json else {},
    }


def get_error_summary(hours: int = 24) -> list[dict]:
    """获取最近 N 小时的错误摘要"""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    try:
        db = _get_db()
        from models import SystemLog as SystemLogModel
        from sqlalchemy import func
        rows = (
            db.query(
                SystemLogModel.category,
                SystemLogModel.message,
                func.count(SystemLogModel.id).label("cnt"),
            )
            .filter(SystemLogModel.level.in_(["error", "critical"]))
            .filter(SystemLogModel.created_at >= cutoff)
            .group_by(SystemLogModel.category, SystemLogModel.message)
            .order_by(func.count(SystemLogModel.id).desc())
            .limit(50)
            .all()
        )
        db.close()
        return [
            {"category": r.category, "message": r.message, "count": r.cnt}
            for r in rows
        ]
    except Exception:
        return []
