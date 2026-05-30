"""
智审通 · 本地推理服务 — 加载 Qwen3 GGUF 模型，自动检测 GPU 加速

GPU 加速策略（自动检测，优先级从高到低）：
  Apple Silicon (M1/M2/M3/M4) → Metal (MPS) 加速
  NVIDIA GPU                   → CUDA (cuBLAS) 加速
  AMD GPU                      → ROCm (hipBLAS) 加速
  无可用 GPU                    → CPU (AVX2 多线程)

暴露 OpenAI 兼容的 /v1/chat/completions 端点，供后端 RAG 服务调用。
"""
import os
import sys
import time
import json
import logging
import platform
import uuid
from threading import Lock

# ============================================================
#  一、GPU 自动检测
# ============================================================

def detect_gpu_backend() -> tuple[str, dict]:
    """
    按优先级自动检测最优 GPU 加速后端。
    返回: (backend_label, llama_cpp_init_kwargs)
    """
    machine = platform.machine().lower()
    system = platform.system().lower()

    # ── Apple Silicon → Metal ──
    if system == "darwin" and machine in ("arm64", "aarch64"):
        print("🍎 检测到 Apple Silicon → 启用 Metal (MPS) GPU 加速")
        return "metal", {"n_gpu_layers": -1}

    # ── NVIDIA → CUDA ──
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0) or "NVIDIA GPU"
            print(f"🟢 检测到 {gpu_name} → 启用 CUDA GPU 加速")
            return "cuda", {"n_gpu_layers": -1}
    except ImportError:
        pass

    # ── AMD → ROCm ──
    try:
        import torch
        if hasattr(torch, 'hip') and torch.hip.is_available():
            print("🟡 检测到 AMD GPU (ROCm) → 启用 ROCm GPU 加速")
            return "rocm", {"n_gpu_layers": -1}
    except Exception:
        pass

    if os.getenv("GGML_HIPBLAS") == "1" or os.getenv("ROCM_PATH"):
        print("🟡 检测到 ROCm 环境变量 → 启用 ROCm GPU 加速")
        return "rocm", {"n_gpu_layers": -1}

    # ── CPU 兜底 ──
    print("⚪ 未检测到 GPU 加速硬件 → 使用 CPU 推理")
    return "cpu", {"n_gpu_layers": 0}


# ============================================================
#  二、日志 & 配置
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("inference_server")

MODEL_PATH = os.getenv(
    "MODEL_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "models", "qwen3-4b.gguf")
)
PORT = int(os.getenv("PORT", "18080"))
N_CTX = int(os.getenv("N_CTX", "2048"))
N_BATCH = int(os.getenv("N_BATCH", "512"))
N_THREADS = int(os.getenv("N_THREADS", str(os.cpu_count() or 4)))
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080,http://127.0.0.1:5173,http://localhost:5173").split(",")
    if origin.strip()
]

logger.info(f"模型文件: {MODEL_PATH}")
logger.info(f"上下文窗口: {N_CTX} tokens")

# ── 检测 GPU ──
gpu_backend, llama_kwargs = detect_gpu_backend()

# ── 导入 llama.cpp 绑定 ──
try:
    from llama_cpp import Llama
except ImportError:
    logger.error("未安装 llama-cpp-python，请执行：")
    logger.error("  Apple Silicon: CMAKE_ARGS=\"-DGGML_METAL=on\" pip install llama-cpp-python")
    logger.error("  NVIDIA GPU:    CMAKE_ARGS=\"-DGGML_CUDA=on\" pip install llama-cpp-python")
    logger.error("  AMD GPU:       CMAKE_ARGS=\"-DGGML_HIPBLAS=on\" pip install llama-cpp-python")
    logger.error("  CPU only:      pip install llama-cpp-python")
    sys.exit(1)

if not os.path.exists(MODEL_PATH):
    logger.error(f"模型文件不存在: {MODEL_PATH}")
    sys.exit(1)

# ── 加载模型 ──
logger.info("正在加载模型（首次可能需要编译着色器，请稍候）...")
t0 = time.time()

model = Llama(
    model_path=MODEL_PATH,
    n_ctx=N_CTX,
    n_batch=N_BATCH,
    n_threads=N_THREADS,
    verbose=False,
    **llama_kwargs,
)

logger.info(f"模型加载完成，耗时 {time.time() - t0:.1f}s | GPU 后端: {gpu_backend}")

inference_lock = Lock()


# ============================================================
#  三、FastAPI 服务定义
# ============================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="智审通 · 本地推理服务", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    temperature: float = 0.3
    max_tokens: int = 512
    stream: bool = False


class ChatResponse(BaseModel):
    id: str = "local-inference"
    object: str = "chat.completion"
    created: int = 0
    model: str = "qwen3-4b-instruct"
    choices: list[dict]


def _build_qwen_prompt(messages: list[ChatMessage]) -> str:
    """构建 Qwen3 ChatML 格式 prompt"""
    parts: list[str] = []
    for msg in messages:
        parts.append(f"<|im_start|>{msg.role}\n{msg.content}<|im_end|>")
    parts.append("<|im_start|>assistant\n")
    return "\n".join(parts)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": "qwen3-4b-instruct",
        "gpu_backend": gpu_backend,
    }


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [{"id": "qwen3-4b-instruct", "object": "model"}],
    }


@app.post("/v1/chat/completions", response_model=ChatResponse)
def chat_completions(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages is required")

    prompt_text = _build_qwen_prompt(req.messages)

    with inference_lock:
        try:
            output = model.create_completion(
                prompt=prompt_text,
                max_tokens=min(req.max_tokens, 1024),
                temperature=req.temperature,
                top_p=0.9,
                stop=["<|im_end|>", "<|im_start|>"],
                echo=False,
            )
        except Exception as exc:
            logger.error(f"推理失败: {exc}")
            raise HTTPException(status_code=500, detail="推理服务暂时不可用")

    try:
        generated = output["choices"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        logger.error(f"推理响应格式异常: {exc}")
        raise HTTPException(status_code=500, detail="推理服务暂时不可用")

    return ChatResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        choices=[{
            "index": 0,
            "message": {"role": "assistant", "content": generated},
            "finish_reason": "stop",
        }],
    )


# ============================================================
#  四、启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    logger.info(f"推理服务已就绪 → http://0.0.0.0:{PORT}")
    logger.info(f"健康检查: http://localhost:{PORT}/health")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
