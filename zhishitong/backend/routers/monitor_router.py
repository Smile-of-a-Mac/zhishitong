"""
管理员监控路由 — 系统健康 / 运行统计 / 日志查看 / 错误摘要
"""
import datetime, time, os, json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import User, ApprovalRecord, SystemLog, ApiKey, ApprovalStatus, TierEnum
from schemas import (
    SystemHealth, ServiceStatus, SystemStats,
    SystemLogOut, ErrorSummary,
)
from auth import require_admin
from services.logging_service import get_recent_logs, get_error_summary
from config import LLAMA_SERVER_URL

router = APIRouter(prefix="/api/admin/monitor", tags=["monitor"])

_START_TIME = time.time()


# ========== 探活辅助 ==========

def _check_url(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """检测 HTTP 服务是否可达"""
    import urllib.request
    try:
        req = urllib.request.Request(f"{url}/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True, json.loads(resp.read()).get("status", "ok")
            return False, f"HTTP {resp.status}"
    except Exception as e:
        return False, str(e)


def _check_easyocr() -> tuple[bool, str]:
    """检测 EasyOCR 是否可用"""
    try:
        import easyocr
        return True, f"easyocr {easyocr.__version__}"
    except ImportError:
        return False, "easyocr 未安装"
    except Exception as e:
        return False, str(e)


# ========== 系统健康 ==========

@router.get("/health", response_model=SystemHealth)
def system_health(
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    services: list[ServiceStatus] = []
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 1. 数据库
    try:
        db.execute(func.now())
        db_status = "ok"
    except Exception:
        db_status = "error"

    # 2. 推理服务
    inf_ok, inf_detail = _check_url(LLAMA_SERVER_URL)
    services.append(ServiceStatus(
        name="推理服务 (llama.cpp)",
        status="ok" if inf_ok else "down",
        detail=inf_detail,
        checked_at=now,
    ))

    # 3. EasyOCR
    ocr_ok, ocr_detail = _check_easyocr()
    services.append(ServiceStatus(
        name="EasyOCR",
        status="ok" if ocr_ok else "down",
        detail=ocr_detail,
        checked_at=now,
    ))

    # 4. API Key 池
    active_keys = db.query(ApiKey).filter(ApiKey.is_active == True).count()
    services.append(ServiceStatus(
        name="API Key 池",
        status="ok" if active_keys > 0 else "degraded",
        detail=f"活跃 Key: {active_keys} 个",
        checked_at=now,
    ))

    # 5. 数据库连接池
    services.append(ServiceStatus(
        name="数据库",
        status=db_status,
        detail="SQLite" if "sqlite" in str(db.bind.url) else "PostgreSQL",
        checked_at=now,
    ))

    # 综合判定
    down_count = sum(1 for s in services if s.status == "down")
    if down_count >= 2:
        overall = "critical"
    elif down_count >= 1 or db_status != "ok":
        overall = "degraded"
    else:
        overall = "healthy"

    # 磁盘
    disk_pct = None
    try:
        st = os.statvfs("/")
        disk_pct = round((1 - st.f_bavail / st.f_blocks) * 100, 1)
    except Exception:
        pass

    return SystemHealth(
        overall=overall,
        services=services,
        uptime_seconds=round(time.time() - _START_TIME),
        db_status=db_status,
        disk_usage_percent=disk_pct,
    )


# ========== 运行统计 ==========

@router.get("/stats", response_model=SystemStats)
def system_stats(
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    today = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    total_users = db.query(User).count()
    active_today = db.query(User).filter(User.created_at >= today).count()

    # OCR 调用统计
    ocr_today = db.query(ApprovalRecord).filter(ApprovalRecord.created_at >= today).count()

    # 各层级 OCR 调用
    ocr_by_tier = {}
    for tier in TierEnum:
        cnt = (
            db.query(ApprovalRecord)
            .join(User, ApprovalRecord.user_id == User.id)
            .filter(ApprovalRecord.created_at >= today)
            .filter(User.tier == tier)
            .count()
        )
        ocr_by_tier[tier.value] = cnt

    # 审批统计
    approvals_today = (
        db.query(ApprovalRecord)
        .filter(ApprovalRecord.created_at >= today)
        .count()
    )

    approvals_by_status = {}
    for s in ApprovalStatus:
        cnt = (
            db.query(ApprovalRecord)
            .filter(ApprovalRecord.created_at >= today)
            .filter(ApprovalRecord.status == s)
            .count()
        )
        approvals_by_status[s.value] = cnt

    # 近 24h 错误
    cutoff_24h = now - datetime.timedelta(hours=24)
    errors_24h = (
        db.query(SystemLog)
        .filter(SystemLog.level.in_(["error", "critical"]))
        .filter(SystemLog.created_at >= cutoff_24h)
        .count()
    )

    # 推理服务可用率（简单：最近 1 小时有无成功调用）
    inf_ok, _ = _check_url(LLAMA_SERVER_URL, timeout=2.0)
    inf_uptime = 100.0 if inf_ok else 0.0

    return SystemStats(
        total_users=total_users,
        active_users_today=active_today,
        ocr_calls_today=ocr_today,
        ocr_calls_by_tier=ocr_by_tier,
        approvals_today=approvals_today,
        approvals_by_status=approvals_by_status,
        errors_24h=errors_24h,
        inference_uptime_percent=inf_uptime,
    )


# ========== 日志查看 ==========

@router.get("/logs", response_model=list[SystemLogOut])
def view_logs(
    category: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    admin=Depends(require_admin),
):
    """查看结构化日志，支持按分类/级别筛选"""
    logs = get_recent_logs(category=category, level=level, limit=limit, from_db=True)
    return [
        SystemLogOut(
            id=l.get("id"),
            timestamp=l.get("timestamp", ""),
            category=l.get("category", ""),
            level=l.get("level", ""),
            message=l.get("message", ""),
            user_id=l.get("user_id"),
            record_id=l.get("record_id"),
            duration_ms=l.get("duration_ms"),
            error_trace=l.get("error_trace", "")[:1000] if l.get("error_trace") else None,
            extra=l.get("extra", {}),
        )
        for l in logs
    ]


# ========== 错误摘要 ==========

@router.get("/errors", response_model=list[ErrorSummary])
def error_summary(
    hours: int = Query(24, ge=1, le=168),
    admin=Depends(require_admin),
):
    """近 N 小时错误摘要（去重聚合）"""
    return [
        ErrorSummary(category=e["category"], message=e["message"], count=e["count"])
        for e in get_error_summary(hours=hours)
    ]


# ========== 最近错误详情 ==========

@router.get("/errors/recent", response_model=list[SystemLogOut])
def recent_errors(
    limit: int = Query(20, ge=1, le=100),
    admin=Depends(require_admin),
):
    """最近 N 条错误日志详情（含堆栈）"""
    logs = get_recent_logs(level="error", limit=limit, from_db=True)
    return [
        SystemLogOut(
            id=l.get("id"),
            timestamp=l.get("timestamp", ""),
            category=l.get("category", ""),
            level=l.get("level", ""),
            message=l.get("message", ""),
            user_id=l.get("user_id"),
            record_id=l.get("record_id"),
            duration_ms=l.get("duration_ms"),
            error_trace=l.get("error_trace", ""),
            extra=l.get("extra", {}),
        )
        for l in logs
    ]
