"""OCR 路由 — 图片上传 & 识别"""
import json, logging, time

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from database import get_db
from models import User, QuotaLog, ApprovalRecord, TierEnum
from schemas import OCRResult
from auth import get_current_user
from config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL, LLM_FILL_MODEL
from services.file_service import validate_file, store_file
from services.ocr_service import ocr_with_tier, OCRProvider
from services.template_service import detect_document_type
from services.crypto_service import decrypt
from services.logging_service import LogCategory, log, log_error
from services.key_pool import resolve_key, record_success, record_failure, ResolvedKey
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

    if (
        {"invoice_no", "amount"}.issubset(keys)
        or "invoice_no" in keys
        or "invoice_number" in keys
        or "total_amount" in keys
    ):
        return "reimbursement"
    if {"leave_type", "start_date", "end_date"}.intersection(keys):
        return "leave"
    return None


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

    # 2. 选择 LLM 配置（智能 Key 池）
    ocr_cfg, fill_cfg = _resolve_llm_config(db)

    # 3. 执行 OCR
    quota_remaining = user.llm_ocr_quota - user.llm_ocr_used
    try:
        text, provider, filled_json = await ocr_with_tier(
            content,
            tier=user.tier.value,
            llm_quota_remaining=quota_remaining,
            api_base=ocr_cfg.api_base,
            api_key=ocr_cfg.api_key,
            model=ocr_cfg.model,
            fill_api_base=fill_cfg.api_base,
            fill_api_key=fill_cfg.api_key,
            fill_model=fill_cfg.model,
        )
    except Exception as e:
        # 记录失败（保守：两个 Key 都标记）
        record_failure(db, ocr_cfg.key_id)
        record_failure(db, fill_cfg.key_id)
        log_error(LogCategory.OCR, f"OCR 识别失败: {file.filename}", exc=e, user_id=user.id, tier=user.tier.value)
        raise HTTPException(500, f"OCR 识别失败: {e}")
    
    # 记录成功（两个 Key 的使用量 +1）
    record_success(db, ocr_cfg.key_id)
    if fill_cfg.key_id != ocr_cfg.key_id:
        record_success(db, fill_cfg.key_id)

    duration_ms = round((time.time() - t_start) * 1000)

    # 4. 检测文档类型
    doc_type = detect_document_type(text)
    if not doc_type:
        doc_type = _infer_doc_type_from_filled(filled_json)

    # 5. 扣减配额（Pro 层 LLM OCR）
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
    ocr_tool = f"{provider.value}({ocr_cfg.model})"
    log(
        LogCategory.OCR,
        "info",
        f"OCR 完成 [{ocr_tool}] {file.filename}（待用户确认提交）",
        user_id=user.id,
        duration_ms=duration_ms,
        tier=user.tier.value,
        provider=provider.value,
        model=ocr_cfg.model,
        doc_type=doc_type or "unknown",
        text_len=len(text),
    )

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
