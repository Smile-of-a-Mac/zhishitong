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
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
VENV_UVICORN="$ROOT_DIR/.venv/bin/uvicorn"
VENV_PIP="$ROOT_DIR/.venv/bin/pip"

# ---------- 颜色 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { printf "${GREEN}[✓]${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}[!]${NC} %s\n" "$1"; }
err()  { printf "${RED}[✗]${NC} %s\n" "$1"; }

# ---------- 前置检查 ----------
if [ ! -d "$BACKEND_DIR" ]; then err "未找到后端目录: $BACKEND_DIR"; exit 1; fi
if [ ! -d "$FRONTEND_DIR" ]; then err "未找到前端目录: $FRONTEND_DIR"; exit 1; fi
if [ ! -d "$INFER_DIR" ]; then err "未找到推理服务目录: $INFER_DIR"; exit 1; fi
if [ ! -f "$VENV_PYTHON" ]; then err "未找到虚拟环境 Python: $VENV_PYTHON"; exit 1; fi
if ! command -v node &>/dev/null; then err "未检测到 Node.js，请先安装"; exit 1; fi

# ---------- 1. 后端依赖 ----------
log "安装后端 Python 依赖…"
"$VENV_PIP" install -q -r "$BACKEND_DIR/requirements.txt" 2>&1 | tail -1

# ---------- 2. 推理服务依赖 ----------
log "安装推理服务 Python 依赖…"
"$VENV_PIP" install -q -r "$INFER_DIR/requirements.txt" 2>&1 | tail -1

# ---------- 3. 数据库初始化 ----------
log "初始化数据库 & 种子数据…"
PYTHONPATH="$BACKEND_DIR" "$VENV_PYTHON" "$BACKEND_DIR/seed.py" 2>&1

# ---------- 4. 前端依赖 ----------
log "安装前端 npm 依赖…"
cd "$FRONTEND_DIR"
npm install --silent 2>&1 | tail -1
cd "$ROOT_DIR"

# ---------- 清理旧进程 ----------
cleanup() {
  echo ""
  warn "正在停止服务…"
  [ -n "$INFER_PID" ] && kill "$INFER_PID" 2>/dev/null && log "推理服务已停止"
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null && log "后端已停止"
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null && log "前端已停止"
  exit 0
}
trap cleanup SIGINT SIGTERM

# ---------- 5. 启动推理服务 ----------
log "启动本地推理服务 (llama.cpp + Qwen2.5-0.5B)…"
PYTHONPATH="$INFER_DIR" "$VENV_UVICORN" server:app \
  --host 0.0.0.0 --port 18080 &
INFER_PID=$!

for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:18080/health >/dev/null 2>&1; then
    log "推理服务就绪 → http://localhost:18080"
    break
  fi
  [ $i -eq 60 ] && warn "推理服务启动较慢（首次需加载模型到内存，请耐心等待）…"
  sleep 2
done

# ---------- 6. 启动后端 ----------
log "启动后端 (uvicorn)…"
PYTHONPATH="$BACKEND_DIR" "$VENV_UVICORN" main:app \
  --host 0.0.0.0 --port 8080 --reload &
BACKEND_PID=$!

for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8080/api/docs >/dev/null 2>&1; then
    log "后端就绪 → http://localhost:8080"
    break
  fi
  [ $i -eq 30 ] && warn "后端启动较慢，仍在等待…"
  sleep 1
done

# ---------- 7. 启动前端 ----------
log "启动前端 (vite dev server)…"
cd "$FRONTEND_DIR"
npx vite --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!
cd "$ROOT_DIR"

for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:5173 >/dev/null 2>&1; then
    log "前端就绪 → http://localhost:5173"
    break
  fi
  sleep 1
done

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
echo "  账号                        密码          角色 / 学校"
echo "  admin                       admin123      超级管理员"
echo "  sdu_school_admin            admin123      学校管理员 (山东科技大学)"
echo "  sdu_dept_cs                 123456        部门管理员 (山东科技大学)"
echo "  sdu_finance_admin           admin123      财务管理员 (山东科技大学)"
echo "  sdu_student_a / sdu_student_b  123456    学生 (山东科技大学)"
echo "  sdujn_school_admin          admin123      学校管理员 (济南校区)"
echo "  sdujn_dept_cs               123456        部门管理员 (济南校区)"
echo "  sdujn_finance_admin         admin123      财务管理员 (济南校区)"
echo "  sdujn_student_a / sdujn_student_b  123456  学生 (济南校区)"
echo ""
echo "  按 Ctrl+C 同时停止所有服务"
echo "========================================"

wait
