#!/usr/bin/env bash
# ================================
#  智审通 — 一键停止脚本
#  停止 start.sh 启动的所有服务
#  用法:  cd zhishitong && bash shutdown.sh
# ================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { printf "${GREEN}[✓]${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}[!]${NC} %s\n" "$1"; }
err()  { printf "${RED}[✗]${NC} %s\n" "$1"; }

# ── 按端口号查找进程并终止 ──
kill_by_port() {
  local port=$1 name=$2
  local pid
  pid=$(lsof -ti :"$port" 2>/dev/null)
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null
    # 等待最多 3 秒让进程退出
    for _ in $(seq 1 3); do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 1
    done
    # 如果还没退出，强制 kill
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null
      warn "$name (pid $pid) 已强制停止"
    else
      log "$name 已停止"
    fi
  else
    warn "$name 未运行"
  fi
}

# ── 按进程名模糊查找并终止（兜底） ──
kill_by_name() {
  local pattern=$1 name=$2
  local pids
  pids=$(pgrep -f "$pattern" 2>/dev/null | grep -v "grep\|$$" || true)
  if [ -n "$pids" ]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null
    sleep 1
    # shellcheck disable=SC2086
    if kill -0 $pids 2>/dev/null 2>&1; then
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null
      warn "$name 已强制停止"
    else
      log "$name 已停止"
    fi
  fi
}

echo ""
echo "========================================"
echo "  智审通 — 正在停止所有服务"
echo "========================================"
echo ""

# ── 1. 按端口停止（精确） ──
kill_by_port 18080 "推理服务 (llama.cpp)"
kill_by_port 8080  "后端 (uvicorn)"
kill_by_port 5173  "前端 (vite)"

# ── 2. 按进程名兜底（防止端口查找遗漏） ──
# 部分系统上 lsof 可能查不到 uvicorn 的子进程
kill_by_name "uvicorn.*main:app"  "后端 (uvicorn, 进程名)"
kill_by_name "vite"               "前端 (vite, 进程名)"
kill_by_name "llama-server\|server:app.*18080" "推理服务 (llama.cpp, 进程名)"

echo ""
echo "========================================"
echo "  ✅ 所有服务已停止"
echo "========================================"
