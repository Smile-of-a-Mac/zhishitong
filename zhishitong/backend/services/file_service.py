"""文件服务 — 校验、存储、清理"""
import uuid
import magic
from pathlib import Path
from fastapi import HTTPException, UploadFile
from config import ALLOWED_MIMES, MAX_FILE_SIZE, UPLOAD_DIR


def validate_file(content: bytes) -> str:
    """校验文件 → 返回 MIME 类型"""
    if len(content) == 0:
        raise HTTPException(400, "文件为空")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"文件过大，上限 {MAX_FILE_SIZE // 1024 // 1024} MB")

    detected = magic.from_buffer(content[:2048], mime=True)
    if detected not in ALLOWED_MIMES:
        raise HTTPException(400, f"不支持的文件类型: {detected}")

    return detected


def store_file(content: bytes, mime_type: str, user_id: int) -> str:
    """
    安全存储文件，返回相对 storage_path。
    隔离路径: uploads/{user_id}/YYYY-MM/{uuid}.{ext}
    """
    from datetime import date

    ext_map = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    ext = ext_map.get(mime_type, ".bin")
    safe_name = f"{uuid.uuid4().hex}{ext}"

    today = date.today().strftime("%Y-%m")
    dir_path = UPLOAD_DIR / str(user_id) / today
    dir_path.mkdir(parents=True, exist_ok=True)

    file_path = dir_path / safe_name
    file_path.write_bytes(content)

    return str(file_path.relative_to(UPLOAD_DIR.parent))


def resolve_storage_path(storage_path: str) -> Path:
    """Resolve a stored upload path and ensure it cannot escape UPLOAD_DIR."""
    base = UPLOAD_DIR.resolve()
    full = (UPLOAD_DIR.parent / storage_path).resolve()
    try:
        full.relative_to(base)
    except ValueError:
        raise HTTPException(403, "非法文件路径")
    return full


def delete_physical(storage_path: str) -> None:
    """物理删除文件"""
    full = resolve_storage_path(storage_path)
    if full.exists():
        full.unlink()
