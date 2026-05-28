"""加密服务 — Fernet 对称加密"""
import base64, os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from config import ENCRYPTION_KEY

_FERNET: Fernet | None = None
_FALLBACK_KEY_FILE = Path(__file__).resolve().parent / ".encryption_key"


def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is None:
        key = ENCRYPTION_KEY
        if not key:
            # 若环境变量未设置，尝试从文件读取或生成持久化 key
            if _FALLBACK_KEY_FILE.exists():
                key = _FALLBACK_KEY_FILE.read_text().strip()
            else:
                key = Fernet.generate_key().decode()
                _FALLBACK_KEY_FILE.write_text(key)
                # 确保文件权限仅所有者可读
                _FALLBACK_KEY_FILE.chmod(0o600)
                import logging
                logging.getLogger(__name__).info(f"已自动生成加密密钥: {_FALLBACK_KEY_FILE}")
        _FERNET = Fernet(key.encode() if isinstance(key, str) else key)
    return _FERNET


def encrypt(plaintext: str) -> str:
    """加密明文，返回 Base64 密文字符串"""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """解密密文，返回明文"""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("解密失败：密钥不匹配或数据已损坏")


def generate_key() -> str:
    """生成一个新的 Fernet 密钥"""
    return Fernet.generate_key().decode()
