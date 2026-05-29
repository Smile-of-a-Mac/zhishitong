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
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

log()  { printf "${GREEN}[✓]${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}[!]${NC} %s\n" "$1"; }
err()  { printf "${RED}[✗]${NC} %s\n" "$1"; }

# ── 按端口号查找进程并终止 ──
kill_by_port() {
  local port=$1 name=$2
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -z "$pids" ]; then
    warn "$name 未运行"
    return
  fi

  local pid
  for pid in $pids; do
    kill_one "$pid" "$name"
  done
}

kill_one() {
  local pid=$1 name=$2
  if [ -z "$pid" ] || [ "$pid" = "$$" ] || ! kill -0 "$pid" 2>/dev/null; then
    return
  fi

  pkill -TERM -P "$pid" 2>/dev/null || true
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 3); do
    if ! kill -0 "$pid" 2>/dev/null; then
      log "$name (pid $pid) 已停止"
      return
    fi
    sleep 1
  done

  if kill -0 "$pid" 2>/dev/null; then
    pkill -KILL -P "$pid" 2>/dev/null || true
    kill -9 "$pid" 2>/dev/null || true
    warn "$name (pid $pid) 已强制停止"
  fi
}

# ── 按进程名模糊查找并终止（兜底） ──
kill_by_name() {
  local pattern=$1 name=$2
  local pids
  pids=$(pgrep -f "$pattern" 2>/dev/null || true)
  if [ -z "$pids" ]; then
    return
  fi

  local pid
  for pid in $pids; do
    kill_one "$pid" "$name"
  done
}

echo ""
echo "========================================"
echo "  智审通 — 正在停止所有服务"
echo "========================================"
echo ""

# ── 1. 优先按本项目路径停止，降低误杀其他服务的概率 ──
kill_by_name "$ROOT_DIR/inference_server.*server:app" "推理服务 (本项目)"
kill_by_name "$ROOT_DIR/backend.*main:app"           "后端 (本项目)"
kill_by_name "$ROOT_DIR/frontend.*vite"              "前端 (本项目)"

# ── 2. 按端口兜底。若端口被其他项目占用，这里仍可能停止该端口进程。 ──
kill_by_port 18080 "推理服务 (端口 18080)"
kill_by_port 8080  "后端 (端口 8080)"
kill_by_port 5173  "前端 (端口 5173)"

echo ""
echo "========================================"
echo "  ✅ 所有服务已停止"
echo "========================================"
