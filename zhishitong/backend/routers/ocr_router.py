"""OCR 路由 — 图片上传 & 识别"""
import asyncio, json, logging, time

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from database import get_db
from models import User, QuotaLog, ApprovalRecord, TierEnum
from schemas import OCRResult
from auth import get_current_user
from config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL, LLM_FILL_MODEL
from services.file_service import validate_file, store_file
from services.ocr_service import ocr_with_tier, OCRProvider, _postprocess_leave_fields
from services.template_service import detect_document_type
from services.crypto_service import decrypt
from services.logging_service import LogCategory, log, log_error
from services.key_pool import resolve_key, record_success, record_failure, ResolvedKey
from services.redis_service import ocr_cache_get, ocr_cache_set, rate_limit_check
from services.redis_service import RATE_LIMIT_WINDOW as _RL_WINDOW
from models import ApiKeyType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ocr"])

def _infer_doc_type_from_filled(filled_json: dict | None) -> str | None:
    """当原文检测失败时，根据已提取字段反推文档类型。"""
    if not isinstance(filled_json, dict):
        return None

    keys = {k for k, v in filled_json.items() if v not in (None, "", [], {})}
    if not keys:
        return None

    # ── 报销：金额 + 发票号 / 金额 + 事由 / 单金额兜底 ──
    if (
        {"invoice_no", "amount"}.issubset(keys)
        or "invoice_no" in keys
        or "invoice_number" in keys
        or "total_amount" in keys
        or ("amount" in keys and len(keys) >= 2)  # 金额 + 至少一个其他字段
        or ("amount" in keys and "reason" in keys)
    ):
        return "reimbursement"

    # ── 请假：请假类型 / 起止日期 / duration / 去向+交通工具+事由 ──
    if (
        "leave_type" in keys
        or ({"start_date", "end_date"}.issubset(keys) and "reason" in keys)
        or {"leave_type", "start_date", "end_date", "duration"}.intersection(keys)
        or ("destination" in keys and "transportation" in keys)
        or ("advisor" in keys and "reason" in keys and "destination" in keys)
    ):
        return "leave"

    # ── 社团活动：社团名 / 活动名 ──
    if {"club_name", "activity"}.intersection(keys):
        return "club_application"

    # ── 教室借用：教室编号 ──
    if "room_no" in keys:
        return "classroom_booking"

    # ── 出差：目的地 + 出差事由 ──
    if "destination" in keys and ("purpose" in keys or "estimated_cost" in keys):
        return "business_trip"

    # ── 用章：印章类型 / 用印文件 ──
    if {"seal_type", "document_name"}.intersection(keys):
        return "seal_application"

    # ── 宿舍调换：宿舍相关字段 ──
    if {"dorm_from", "dorm_to"}.intersection(keys):
        return "dorm_change"

    # ── 奖学金：奖学金类型 / GPA ──
    if {"scholarship_type", "gpa", "rank"}.intersection(keys):
        return "scholarship"

    # ── 休学/复学 ──
    if "suspend_type" in keys:
        return "suspend_resume"

    # ── 在读证明 ──
    if "enrollment_date" in keys and "expected_grad" in keys:
        return "enrollment_proof"

    # ── 出国申请 ──
    if {"country", "visa_type", "passport_no"}.intersection(keys):
        return "abroad_application"

    # ── 成绩单/学历学位 ──
    if "gpa" in keys and "major" in keys:
        return "transcript_print"

    # ── 如果仅有 applicant + amount，大概率是报销 ──
    if "applicant" in keys and "amount" in keys and len(keys) <= 3:
        return "reimbursement"

    return None


# 所有模板已知 key 的白名单，用于过滤 LLM 垃圾输出
_KNOWN_FIELD_KEYS: set[str] = {
    "applicant", "amount", "invoice_no", "date", "category", "reason", "department",
    "college", "class_name", "student_id", "phone", "leave_type", "start_date",
    "end_date", "days", "duration", "destination", "transportation", "advisor", "advisor_phone",
    "parent_phone", "club_name", "club_type", "activity", "purpose", "start_time",
    "end_time", "venue", "participants", "budget", "description", "room_no",
    "need_multimedia", "estimated_cost", "accommodation", "international",
    "seal_type", "document_name", "copies", "recipient", "notes",
    "dorm_from", "dorm_to", "roommates", "suspend_type", "expected_duration",
    "scholarship_type", "gpa", "rank", "award_level", "enrollment_date",
    "expected_grad", "usage", "country", "visa_type", "passport_no",
    "employee_id", "position", "entry_date", "item_list", "quantity", "unit_price",
    "isbn", "book_title", "author", "publisher", "language", "course_name",
    "class_id", "reschedule_type", "original_date", "original_time",
    "new_date", "new_time", "affected_classes", "exam_type", "original_exam_date",
    "major", "title", "tax", "name",
}


def _sanitize_filled_json(filled_json: dict | None) -> dict | None:
    """
    过滤 LLM 返回的垃圾 JSON。
    只保留白名单字段，且至少有一个非空值，否则返回 None。
    """
    if not isinstance(filled_json, dict):
        return None
    # 过滤掉明显的 API 响应结构（如 {"code":200, "data":{...}}）
    if "code" in filled_json or "status" in filled_json or "data" in filled_json:
        return None
    cleaned = {
        k: v for k, v in filled_json.items()
        if k in _KNOWN_FIELD_KEYS and v not in (None, "", [], {})
    }
    return cleaned if cleaned else None


def _resolve_llm_config(db: Session) -> tuple:
    """从 Key 池智能选取最优 Key，返回 (ocr_resolved, fill_resolved)"""
    ocr_resolved = resolve_key(
        db, ApiKeyType.ocr,
        fallback_base=LLM_API_BASE, fallback_key=LLM_API_KEY, fallback_model=LLM_MODEL,
    )
    fill_resolved = resolve_key(
        db, ApiKeyType.json_fill,
        fallback_base=LLM_API_BASE, fallback_key=LLM_API_KEY, fallback_model=LLM_FILL_MODEL,
    )
    return ocr_resolved, fill_resolved


def _model_used_for_provider(provider: OCRProvider, ocr_cfg: ResolvedKey, fill_cfg: ResolvedKey) -> str:
    """Return the model that was actually used for the reported OCR provider."""
    if provider == OCRProvider.PDF_TEXT:
        return fill_cfg.model
    return ocr_cfg.model


@router.post("/ocr", response_model=OCRResult)
async def ocr_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t_start = time.time()

    # 1. 校验 & 存储文件
    try:
        content = await file.read()
        mime = validate_file(content)
        storage_path = store_file(content, mime, user.id)
    except HTTPException:
        raise
    except Exception as e:
        log_error(LogCategory.OCR, f"文件处理失败: {file.filename}", exc=e, user_id=user.id, filename=file.filename)
        raise HTTPException(500, f"文件处理失败: {e}")

    # 1.5 速率限制
    allowed, remaining_rl = await rate_limit_check(user.id, user.tier.value)
    if not allowed:
        raise HTTPException(429, f"请求过于频繁，请 {_RL_WINDOW}s 后重试")

    # 1.6 OCR 缓存查询（按用户隔离）
    cached = await ocr_cache_get(content, user_id=user.id)
    if cached:
        duration_ms = round((time.time() - t_start) * 1000)
        cached_quota = max(0, user.llm_ocr_quota - user.llm_ocr_used)
        log(
            LogCategory.OCR,
            "info",
            f"OCR 缓存命中 [{cached.get('provider', 'unknown')}] {file.filename}",
            user_id=user.id,
            duration_ms=duration_ms,
            provider=cached.get("provider", ""),
            doc_type=cached.get("document_type", "unknown"),
        )
        return OCRResult(
            text=cached.get("text", ""),
            provider=cached.get("provider", ""),
            tier=user.tier.value,
            quota_remaining=cached_quota if user.tier == TierEnum.pro else None,
            document_type=cached.get("document_type"),
            filled_json=cached.get("filled_json"),
            storage_path=storage_path,
            original_filename=file.filename,
            mime_type=mime,
            file_size=len(content),
        )

    # 2. 选择 LLM 配置（智能 Key 池）
    ocr_cfg, fill_cfg = _resolve_llm_config(db)

    # 3. 执行 OCR
    quota_remaining = user.llm_ocr_quota - user.llm_ocr_used
    try:
        text, provider, filled_json = await ocr_with_tier(
            content,
            tier=user.tier.value,
            llm_quota_remaining=quota_remaining,
            mime_type=mime,
            api_base=ocr_cfg.api_base,
            api_key=ocr_cfg.api_key,
            model=ocr_cfg.model,
            fill_api_base=fill_cfg.api_base,
            fill_api_key=fill_cfg.api_key,
            fill_model=fill_cfg.model,
        )
    except ValueError as e:
        log_error(LogCategory.OCR, f"OCR 识别失败: {file.filename}", exc=e, user_id=user.id, tier=user.tier.value)
        raise HTTPException(400, str(e))
    except Exception as e:
        # 记录失败（保守：两个 Key 都标记）
        record_failure(db, ocr_cfg.key_id)
        record_failure(db, fill_cfg.key_id)
        log_error(LogCategory.OCR, f"OCR 识别失败: {file.filename}", exc=e, user_id=user.id, tier=user.tier.value)
        raise HTTPException(500, f"OCR 识别失败: {e}")
    
    # 记录成功（仅当实际使用了 LLM 多模态时才记录 OCR Key）
    if provider == OCRProvider.LLM:
        record_success(db, ocr_cfg.key_id)
        # 多模态一步完成时，fill key 未使用，不记录
    elif provider == OCRProvider.PDF_TEXT:
        # 文本型 PDF 使用文本抽取 + JSON LLM 填充，不消耗多模态 OCR Key
        record_success(db, fill_cfg.key_id)
    elif provider == OCRProvider.LOCAL:
        # EasyOCR 降级时，可能用了外部 fill key；但此处不追踪 fill key 的成功
        pass

    duration_ms = round((time.time() - t_start) * 1000)

    # 4. 清洗 filled_json：过滤 LLM 垃圾输出
    filled_json = _sanitize_filled_json(filled_json)

    # 5. 检测文档类型
    doc_type = detect_document_type(text)
    if not doc_type:
        doc_type = _infer_doc_type_from_filled(filled_json)
    if doc_type == "leave" and filled_json:
        filled_json = _postprocess_leave_fields(filled_json, text)

    # 6. 扣减配额（Pro 层多模态 LLM OCR；文本型 PDF 只走 JSON 填充，不扣 OCR 配额）
    if provider == OCRProvider.LLM and user.tier == TierEnum.pro:
        locked_user = db.query(User).filter(User.id == user.id).with_for_update().first()
        locked_user.llm_ocr_used += 1
        db.add(QuotaLog(
            user_id=user.id, action="llm_ocr",
            detail=f"第 {locked_user.llm_ocr_used} 次 LLM OCR",
        ))
        db.commit()

    remaining = max(0, user.llm_ocr_quota - user.llm_ocr_used)

    # 7. 结构化日志（不创建审批记录，等用户确认后再提交）
    used_model = _model_used_for_provider(provider, ocr_cfg, fill_cfg)
    ocr_tool = f"{provider.value}({used_model})"
    log(
        LogCategory.OCR,
        "info",
        f"OCR 完成 [{ocr_tool}] {file.filename}（待用户确认提交）",
        user_id=user.id,
        duration_ms=duration_ms,
        tier=user.tier.value,
        provider=provider.value,
        model=used_model,
        doc_type=doc_type or "unknown",
        text_len=len(text),
    )

    # 8. 写入 OCR 缓存（异步，不阻塞响应）
    cache_data = {
        "text": text,
        "provider": provider.value,
        "document_type": doc_type,
        "filled_json": filled_json,
    }
    asyncio.create_task(ocr_cache_set(content, cache_data, user_id=user.id))

    return OCRResult(
        text=text,
        provider=provider.value,
        tier=user.tier.value,
        quota_remaining=remaining if user.tier == TierEnum.pro else None,
        document_type=doc_type,
        filled_json=filled_json,
        # 附带文件信息供后续提交使用
        storage_path=storage_path,
        original_filename=file.filename,
        mime_type=mime,
        file_size=len(content),
    )
