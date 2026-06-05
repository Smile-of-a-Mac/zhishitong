"""应用配置 — 所有可变参数集中管理"""
import os
from pathlib import Path

# ---- 项目根目录 ----
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ---- 安全 ----
_JWT_SECRET_FILE = BASE_DIR / "data" / ".jwt_secret"
_JWT_SECRET = os.getenv("JWT_SECRET", "")

if not _JWT_SECRET:
    # 开发环境：从文件持久化读取，避免 --reload 重启导致密钥变更
    if _JWT_SECRET_FILE.exists():
        _JWT_SECRET = _JWT_SECRET_FILE.read_text().strip()
        if _JWT_SECRET:
            print(f"\033[90m[信息] JWT_SECRET 已从 {_JWT_SECRET_FILE} 加载\033[0m")

if not _JWT_SECRET:
    import secrets
    _JWT_SECRET = secrets.token_urlsafe(48)
    # 持久化写入文件，确保 --reload 重启后密钥不变
    _JWT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _JWT_SECRET_FILE.write_text(_JWT_SECRET)
    print("\n\033[93m[安全警告] JWT_SECRET 未设置环境变量，已自动生成随机密钥并持久化到文件。")
    print(f"密钥文件: {_JWT_SECRET_FILE}")
    print("生产环境请务必设置 JWT_SECRET 环境变量。\033[0m\n")
JWT_SECRET = _JWT_SECRET
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
JWT_ACCESS_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "30"))
JWT_REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))
ENFORCE_SECRETS = os.getenv("ENFORCE_SECRETS", "false").lower() == "true"

if ENFORCE_SECRETS:
    WEAK_SECRET_MARKERS = {"change-in-production", "dev-secret", "default", "example"}
    if not JWT_SECRET or len(JWT_SECRET) < 24 or any(marker in JWT_SECRET.lower() for marker in WEAK_SECRET_MARKERS):
        raise RuntimeError("生产模式下 JWT_SECRET 不合法：请设置足够复杂的环境变量 JWT_SECRET")

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
"""
Fernet 加密密钥。
生成方式: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
部署时必须设置环境变量。
"""
APP_ENV = os.getenv("APP_ENV", "development")
if APP_ENV == "production" and not ENCRYPTION_KEY:
    raise RuntimeError(
        "生产环境必须设置 ENCRYPTION_KEY 环境变量。"
        "生成方式: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )
if not ENCRYPTION_KEY and APP_ENV != "production":
    print("\n\033[93m[安全警告] ENCRYPTION_KEY 未设置环境变量，加密功能将不可用。"
          "生产环境请务必设置 ENCRYPTION_KEY。\033[0m\n")

# ---- 网络 ----
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:8080,http://localhost:8080").split(",")
    if origin.strip()
]

# ---- 数据库 ----
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{(BASE_DIR / 'data' / 'zhishitong.db').as_posix()}",
)
# 确保 SQLite 数据目录存在
if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

# ---- 本地模型推理服务 (llama.cpp) ----
LLAMA_SERVER_URL = os.getenv("LLAMA_SERVER_URL", "http://127.0.0.1:18080")
LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH", "")

# ---- 外部 LLM API ----
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-vl-plus")
LLM_FILL_MODEL = os.getenv("LLM_FILL_MODEL", "qwen-plus")

# ---- 文件上传 ----
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "10")) * 1024 * 1024

# ---- API Key 池上限 ----
MAX_OCR_KEYS = int(os.getenv("MAX_OCR_KEYS", "100"))
MAX_FILL_KEYS = int(os.getenv("MAX_FILL_KEYS", "100"))
MAX_LLM_KEYS = int(os.getenv("MAX_LLM_KEYS", "100"))

# ---- EasyOCR ----
EASYOCR_LANGS = ["ch_sim", "en"]
EASYOCR_GPU = os.getenv("EASYOCR_GPU", "false").lower() == "true"

# ---- Redis ----
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
OCR_CACHE_TTL = int(os.getenv("OCR_CACHE_TTL", str(24 * 3600)))  # OCR 缓存 TTL（秒）
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

# ---- 模板文件 ----
TEMPLATES_PATH = Path(__file__).resolve().parent / "templates.json"

# ---- RAG ----
RAG_CACHE_PATH = os.getenv(
    "RAG_CACHE_PATH",
    (BASE_DIR / "data" / "rag_tfidf_cache.pkl").as_posix(),
)
