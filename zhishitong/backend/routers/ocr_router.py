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

    # 4. 扣减配额（Pro 层 LLM OCR）
    if provider == OCRProvider.LLM and user.tier == TierEnum.pro:
        # 以行锁重新读取，防止并发竞态造成超额
        locked_user = db.query(User).filter(User.id == user.id).with_for_update().first()
        locked_user.llm_ocr_used += 1
        db.add(QuotaLog(
            user_id=user.id, action="llm_ocr",
            detail=f"第 {locked_user.llm_ocr_used} 次 LLM OCR",
        ))

    # 5. 检测文档类型
    doc_type = detect_document_type(text)

    # 6. 确定初始审批阶段
    from services.workflow import get_first_stage
    first_stage = get_first_stage(doc_type, filled_json)

    # 7. 保存 OCR 记录
    record = ApprovalRecord(
        user_id=user.id,
        original_filename=file.filename,
        storage_path=storage_path,
        mime_type=mime,
        file_size=len(content),
        ocr_provider=provider.value,
        ocr_model=ocr_cfg.model if provider == OCRProvider.LLM else (
            f"easyocr+{fill_cfg.model}" if fill_cfg.api_key else "easyocr+qwen3-0.5b"
        ),
        raw_ocr_text=text,
        filled_json=json.dumps(filled_json, ensure_ascii=False) if filled_json else None,
        document_type=doc_type,
        current_stage=first_stage,
        stage_history_json="[]",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    remaining = max(0, user.llm_ocr_quota - user.llm_ocr_used)

    # 结构化日志
    ocr_tool = f"{provider.value}({record.ocr_model})"
    log(
        LogCategory.OCR,
        "info",
        f"OCR 完成 [{ocr_tool}] {file.filename}",
        user_id=user.id,
        record_id=record.id,
        duration_ms=duration_ms,
        tier=user.tier.value,
        provider=provider.value,
        model=record.ocr_model,
        doc_type=doc_type or "unknown",
        text_len=len(text),
        has_filled_json=filled_json is not None and "error" not in str(filled_json),
    )

    return OCRResult(
        text=text,
        provider=provider.value,
        tier=user.tier.value,
        quota_remaining=remaining if user.tier == TierEnum.pro else None,
        document_type=doc_type,
        filled_json=filled_json,
        record_id=record.id,
    )
