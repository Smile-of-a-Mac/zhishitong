#!/usr/bin/env bash
# ================================
#  智审通 — 一键启动脚本
#  自动完成：安装依赖 → 初始化数据 → 启动推理服务 → 启动前后端
#  用法:  cd zhishitong && bash start.sh
# ================================
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
INFER_DIR="$ROOT_DIR/inference_server"
VENV_PYTHON="$ROOT_DIR/../.venv/bin/python"
VENV_UVICORN="$ROOT_DIR/../.venv/bin/uvicorn"
VENV_PIP="$ROOT_DIR/../.venv/bin/pip"

# ---------- 颜色 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { printf "${GREEN}[✓]${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}[!]${NC} %s\n" "$1"; }
err()  { printf "${RED}[✗]${NC} %s\n" "$1"; }

run_step() {
  local label=$1
  shift
  log "$label"
  if ! "$@"; then
    err "$label 失败"
    exit 1
  fi
}

stop_process_tree() {
  local pid=$1 name=$2
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    return
  fi
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill "$pid" 2>/dev/null || true
  log "$name 已停止"
}

# ---------- 前置检查 ----------
if [ ! -d "$BACKEND_DIR" ]; then err "未找到后端目录: $BACKEND_DIR"; exit 1; fi
if [ ! -d "$FRONTEND_DIR" ]; then err "未找到前端目录: $FRONTEND_DIR"; exit 1; fi
if [ ! -d "$INFER_DIR" ]; then err "未找到推理服务目录: $INFER_DIR"; exit 1; fi
if [ ! -f "$VENV_PYTHON" ]; then err "未找到虚拟环境 Python: $VENV_PYTHON"; exit 1; fi
if ! command -v node &>/dev/null; then err "未检测到 Node.js，请先安装"; exit 1; fi

# ---------- JWT 密钥持久化 ----------
# 确保 JWT_SECRET 跨重启不变（优先从文件读取，否则自动生成并持久化）
JWT_SECRET_FILE="$BACKEND_DIR/data/.jwt_secret"
if [ -f "$JWT_SECRET_FILE" ]; then
  JWT_SECRET=$(cat "$JWT_SECRET_FILE")
  export JWT_SECRET
  log "JWT_SECRET 已从 $JWT_SECRET_FILE 加载"
else
  # 确保 data 目录存在
  mkdir -p "$BACKEND_DIR/data"
  # 生成随机密钥并写入文件（config.py 也会做同样的事，但提前设置可以避免首次启动时密钥变更）
  JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  echo "$JWT_SECRET" > "$JWT_SECRET_FILE"
  export JWT_SECRET
  log "JWT_SECRET 已自动生成并持久化到 $JWT_SECRET_FILE"
fi

# ---------- Redis 检查 ----------
log "检查 Redis 连接…"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
if command -v redis-cli &>/dev/null; then
  if redis-cli -u "$REDIS_URL" ping 2>/dev/null | grep -q "PONG"; then
    log "Redis 连接正常"
  else
    warn "Redis 无法连接（$REDIS_URL），部分功能（缓存/限流/通知）可能不可用"
  fi
else
  warn "未安装 redis-cli，跳过 Redis 检查。部分功能（缓存/限流/通知）可能不可用"
fi

# ---------- 1. 后端依赖 ----------
if "$VENV_PYTHON" -c "import fastapi, sqlalchemy, jose, passlib" 2>/dev/null; then
  log "后端 Python 依赖已就绪，跳过 pip install"
else
  run_step "安装后端 Python 依赖…" "$VENV_PIP" install -r "$ROOT_DIR/../requirements.txt"
fi

# ---------- 2. 推理服务依赖 ----------
if "$VENV_PYTHON" -c "import llama_cpp, huggingface_hub" 2>/dev/null; then
  log "推理服务 Python 依赖已就绪，跳过 pip install"
else
  run_step "安装推理服务 Python 依赖…" "$VENV_PIP" install -r "$INFER_DIR/requirements.txt"
fi

# ---------- 2.5 训练可选依赖 ----------
if [ -f "$ROOT_DIR/../training/train_requirements.txt" ]; then
  if "$VENV_PYTHON" -c "import torch, transformers, peft" 2>/dev/null; then
    log "训练 Python 依赖已就绪，跳过 pip install"
  else
    run_step "安装训练 Python 依赖…" "$VENV_PIP" install -r "$ROOT_DIR/../training/train_requirements.txt"
  fi
fi

# ---------- 3. 数据库初始化 ----------
log "初始化数据库 & 种子数据…"
PYTHONPATH="$BACKEND_DIR" "$VENV_PYTHON" "$BACKEND_DIR/seed.py" 2>&1

# ---------- 4. 前端依赖 ----------
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  run_step "安装前端 npm 依赖…" npm --prefix "$FRONTEND_DIR" install
else
  log "前端 node_modules 已存在，跳过 npm install"
fi

# ---------- 清理旧进程 ----------
cleanup() {
  local code=${1:-0}
  echo ""
  warn "正在停止服务…"
  stop_process_tree "$INFER_PID" "推理服务"
  stop_process_tree "$BACKEND_PID" "后端"
  stop_process_tree "$FRONTEND_PID" "前端"
  exit "$code"
}
trap 'cleanup 0' SIGINT SIGTERM

# ---------- 5. 切换微调模型（如有） ----------
MODELS_DIR="$ROOT_DIR/../models"
LORA_GGUF="$MODELS_DIR/qwen3-4b-lora.gguf"

# merge_lora.py 已直接输出 GGUF，无需额外转换
if [ -f "$LORA_GGUF" ]; then
  export MODEL_PATH="$LORA_GGUF"
  log "使用微调模型: qwen3-4b-lora.gguf"
fi

# ---------- 6. 启动推理服务 ----------
log "启动本地推理服务 (llama.cpp)…"
export MODEL_PATH="${MODEL_PATH:-$MODELS_DIR/qwen3-4b.gguf}"
mkdir -p "$ROOT_DIR/logs"
PYTHONPATH="$INFER_DIR" "$VENV_UVICORN" server:app \
  --host 0.0.0.0 --port 18080 \
  > "$ROOT_DIR/logs/inference.log" 2>&1 &
INFER_PID=$!

INFER_READY=0
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:18080/health >/dev/null 2>&1; then
    log "推理服务就绪 → http://localhost:18080"
    INFER_READY=1
    break
  fi
  sleep 2
done
if [ "$INFER_READY" -ne 1 ]; then
  err "推理服务启动超时，请检查模型路径和 inference_server 依赖"
  cleanup 1
fi

# ---------- 7. 启动后端 ----------
log "启动后端 (uvicorn)…"
mkdir -p "$ROOT_DIR/logs"
PYTHONPATH="$BACKEND_DIR" JWT_SECRET="$JWT_SECRET" "$VENV_UVICORN" main:app \
  --host 0.0.0.0 --port 8080 --reload \
  > "$ROOT_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!

BACKEND_READY=0
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8080/api/health >/dev/null 2>&1; then
    log "后端就绪 → http://localhost:8080"
    BACKEND_READY=1
    break
  fi
  sleep 1
done
if [ "$BACKEND_READY" -ne 1 ]; then
  err "后端启动超时，请检查后端日志"
  cleanup 1
fi

# ---------- 8. 启动前端 ----------
log "启动前端 (vite dev server)…"
cd "$FRONTEND_DIR"
npx vite --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!
cd "$ROOT_DIR"

FRONTEND_READY=0
for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:5173 >/dev/null 2>&1; then
    log "前端就绪 → http://localhost:5173"
    FRONTEND_READY=1
    break
  fi
  sleep 1
done
if [ "$FRONTEND_READY" -ne 1 ]; then
  err "前端启动超时，请检查 Vite 日志"
  cleanup 1
fi

# ---------- 打印信息 ----------
echo ""
echo "========================================"
echo "  智审通 — 开发环境已就绪"
echo "========================================"
echo ""
printf "  前端（推荐）:     ${CYAN}http://localhost:5173${NC}\n"
printf "  后端 API:         ${CYAN}http://localhost:8080/api${NC}\n"
printf "  API 文档:         ${CYAN}http://localhost:8080/api/docs${NC}\n"
printf "  本地推理服务:     ${CYAN}http://localhost:18080${NC}\n"
echo ""
echo "  演示账号: admin、sdu_school_admin、sdu_dept_cs、sdu_finance_admin、sdu_student_a"
echo "  密码由部署方通过 ADMIN_INIT_PASSWORD 或种子数据配置安全分发，不在启动日志中打印。"
echo ""
echo "  按 Ctrl+C 同时停止所有服务"
echo "========================================"

wait
