#!/usr/bin/env bash
# ============================================================================
#  智审通 · macOS / Linux 快速安装脚本
#  功能：预检 → 按需安装 → 汇总报告
#  用法:  cd sito && bash setup/setup.sh
# ============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ---------- 颜色 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; GRAY='\033[2m'; BOLD='\033[1m'; NC='\033[0m'
OK="${GREEN}✓${NC}"; WA="${YELLOW}─${NC}"; ER="${RED}✗${NC}"; SK="${GRAY}⊘${NC}"

# ---------- 报告存储 ----------
R_ITEMS=()   # 每项: "status|title|detail"

report_add() { local s=$1 t=$2 d=$3; R_ITEMS+=("$s|$t|$d"); }

# ---------- 辅助函数 ----------
info()  { echo -e "  ${CYAN}i${NC} $1"; }
ok()    { echo -e "  ${OK}  $1"; }
skip()  { echo -e "  ${SK}  ${GRAY}$1${NC}"; }
warn()  { echo -e "  ${WA}  ${YELLOW}$1${NC}"; }
fail()  { echo -e "  ${ER}  ${RED}$1${NC}"; }
title() { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

check_cmd() { command -v "$1" &>/dev/null; }

append_path() {
  local varname=$1; shift
  for p in "$@"; do
    if [[ -d "$p" && ":${!varname}:" != *":$p:"* ]]; then
      printf -v "$varname" "${!varname}:$p"
    fi
  done
}

cleanup() { [[ -n "${TMP_FILES:-}" ]] && rm -f $TMP_FILES; }
trap cleanup EXIT

# ============================================================
#  1. 标题
# ============================================================
echo ""
echo -e "  ${BOLD}智审通  —  一键环境安装${NC}"
echo -e "  ${GRAY}$ROOT_DIR${NC}"
echo ""

# ============================================================
#  2. 前置检查
# ============================================================
title "前置检查"

# Python
PYTHOK=""
PY_VER=""
for p in python3.12 python3.11 python3.10 python3; do
  if check_cmd "$p"; then
    ver=$("$p" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
    if [[ -n "$ver" && $(echo "$ver" | cut -d. -f1) -ge 3 && $(echo "$ver" | cut -d. -f2) -ge 10 ]]; then
      PYTHOK="$p"; PY_VER=$("$p" --version 2>&1 | head -1); break
    fi
  fi
done
if [ -n "$PYTHOK" ]; then
  ok "Python: $PY_VER"
  report_add "ok" "Python 3.10+" "$PY_VER"
else
  fail "Python 3.10+ 未找到"
  report_add "err" "Python 3.10+" "未安装"
  echo "  请安装: brew install python@3.11 或 apt install python3.11 python3.11-venv"
  echo "  或从 https://www.python.org/downloads/ 下载"
  exit 1
fi

# Node.js
if check_cmd node; then
  NV=$(node --version 2>&1 | head -1)
  ok "Node.js: $NV"
  report_add "ok" "Node.js 18+" "$NV"
else
  fail "Node.js 未找到"
  report_add "err" "Node.js 18+" "未安装"
  echo "  请安装: brew install node@20 或 https://nodejs.org/"
  exit 1
fi

# Git
if check_cmd git; then
  GV=$(git --version 2>&1 | head -1)
  ok "Git: $GV"
  report_add "ok" "Git" "$GV"
else
  warn "Git 未找到"
  report_add "warn" "Git" "未安装（部分功能受限）"
fi

# ============================================================
#  3. 系统能力检测
# ============================================================
title "系统能力检测"

ARCH="$(uname -m)"
OS="$(uname -s)"
ok "系统: $OS $ARCH"

# RAM
if [[ "$OS" == "Darwin" ]]; then
  RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
  RAM_GB=$(echo "scale=1; $RAM_BYTES / 1073741824" | bc)
elif [[ "$OS" == "Linux" ]]; then
  RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
  RAM_GB=$(echo "scale=1; $RAM_KB / 1048576" | bc)
else
  RAM_GB="?"
fi
if [[ "$RAM_GB" != "?" ]]; then
  ok "内存: ${RAM_GB}GB"
else
  warn "无法检测内存"
fi

# Disk
DISK_KB=$(df "$ROOT_DIR" 2>/dev/null | awk 'NR==2 {print $4}' || echo 0)
DISK_GB=$(echo "scale=1; $DISK_KB / 1048576" | bc)
ok "空闲磁盘: ~${DISK_GB}GB"

# GPU & VRAM
GPU=""
VRAM=""
if [[ "$OS" == "Darwin" && "$ARCH" == "arm64" ]]; then
  GPU="Apple Silicon (MPS)"
  # On Apple Silicon, VRAM = shared system memory
  VRAM="shared"
elif check_cmd nvidia-smi; then
  GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "NVIDIA")
  VRAM_MIB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1 | grep -oE '^[0-9]+' || echo "0")
  VRAM=$(echo "scale=1; $VRAM_MIB / 1024" | bc 2>/dev/null || echo "0")
  GPU="NVIDIA $GPU_NAME"
fi
if [ -n "$GPU" ]; then
  if [[ "$VRAM" == "shared" ]]; then
    ok "GPU: $GPU (共享内存 ${RAM_GB}GB)"
  elif [[ -n "$VRAM" && "$VRAM" != "0" ]]; then
    ok "GPU: $GPU (VRAM: ${VRAM}GB)"
  else
    ok "GPU: $GPU"
  fi
else
  warn "未检测到 GPU，推理/训练将使用 CPU"
fi

# Capability decisions
CAN_INFER=false; CAN_TRAIN=false; CAN_DOWNLOAD=false
THRESHOLD_INFER=4.0       # GB (system RAM)
THRESHOLD_TRAIN_CPU=12.0  # GB (system RAM, CPU only)
THRESHOLD_TRAIN_RAM=8.0   # GB (system RAM, with GPU)
THRESHOLD_VRAM_TRAIN=6.0  # GB (GPU VRAM, for LoRA)
THRESHOLD_VRAM_INFER=3.0  # GB (GPU VRAM, for GGUF offloading)
THRESHOLD_DISK=8.0

if [[ "$RAM_GB" != "?" ]]; then
  RAM_OK=$(echo "$RAM_GB >= $THRESHOLD_INFER" | bc)
  if [[ "$RAM_OK" == "1" ]]; then
    CAN_INFER=true
    report_add "ok" "本地推理" "可运行 (RAM ${RAM_GB}GB ≥ ${THRESHOLD_INFER}GB)"
  else
    report_add "skip" "本地推理" "内存不足 (${RAM_GB}GB < ${THRESHOLD_INFER}GB)"
  fi

  # Training check: need enough VRAM (for GPU) or enough RAM (for CPU)
  if [ -n "$GPU" ]; then
    if [[ "$VRAM" == "shared" ]]; then
      # Apple Silicon: unified memory, VRAM = RAM
      TRAIN_OK=$(echo "$RAM_GB >= $THRESHOLD_TRAIN_RAM" | bc)
      TRAIN_REASON="共享内存 ${RAM_GB}GB ≥ ${THRESHOLD_TRAIN_RAM}GB"
    elif [[ -n "$VRAM" && "$VRAM" != "0" ]]; then
      VRAM_OK=$(echo "$VRAM >= $THRESHOLD_VRAM_TRAIN" | bc)
      RAM_OK=$(echo "$RAM_GB >= $THRESHOLD_TRAIN_RAM" | bc)
      if [[ "$VRAM_OK" == "1" && "$RAM_OK" == "1" ]]; then
        TRAIN_OK=1
        TRAIN_REASON="VRAM ${VRAM}GB ≥ ${THRESHOLD_VRAM_TRAIN}GB, RAM ${RAM_GB}GB ≥ ${THRESHOLD_TRAIN_RAM}GB"
      else
        TRAIN_OK=0
        TRAIN_REASON="VRAM ${VRAM}GB < ${THRESHOLD_VRAM_TRAIN}GB 或 RAM ${RAM_GB}GB < ${THRESHOLD_TRAIN_RAM}GB"
      fi
    else
      # GPU present but VRAM unknown
      TRAIN_OK=$(echo "$RAM_GB >= $THRESHOLD_TRAIN_RAM" | bc)
      TRAIN_REASON="VRAM 未知，以 RAM 为准: ${RAM_GB}GB ≥ ${THRESHOLD_TRAIN_RAM}GB"
    fi
  else
    TRAIN_OK=$(echo "$RAM_GB >= $THRESHOLD_TRAIN_CPU" | bc)
    TRAIN_REASON="RAM ${RAM_GB}GB ≥ ${THRESHOLD_TRAIN_CPU}GB (纯 CPU)"
  fi

  if [[ "$TRAIN_OK" == "1" ]]; then
    CAN_TRAIN=true
    report_add "ok" "LoRA 训练" "可运行 ($TRAIN_REASON)"
  else
    report_add "skip" "LoRA 训练" "$TRAIN_REASON"
  fi

  DISK_OK=$(echo "$DISK_GB >= $THRESHOLD_DISK" | bc)
  if [[ "$DISK_OK" == "1" && "$CAN_INFER" == "true" ]]; then
    CAN_DOWNLOAD=true
  fi
fi

if [[ "$CAN_INFER" != "true" ]]; then
  warn "  ⚠ 本机内存不足 ${THRESHOLD_INFER}GB，无法运行本地推理和 LoRA 训练"
  warn "    推荐使用外部 LLM API (Pro 模式) 或升级硬件"
fi

# ============================================================
#  4. 虚拟环境 & Python 依赖（按需安装）
# ============================================================
title "Python 环境"

if [ ! -d "$VENV_DIR" ]; then
  info "创建虚拟环境..."
  "$PYTHOK" -m venv "$VENV_DIR"
  ok "虚拟环境已创建: $VENV_DIR"
  report_add "ok" "Python 虚拟环境" "新建"
else
  skip "虚拟环境已存在: $VENV_DIR"
  report_add "skip" "Python 虚拟环境" "已存在"
fi

"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel -q

# 检测 GPU 并配置 llama-cpp 编译参数
PLATFORM="cpu"
if [ -n "$GPU" ]; then
  if [[ "$GPU" == Apple* ]]; then
    PLATFORM="mps"
  elif [[ "$GPU" == NVIDIA* ]]; then
    PLATFORM="cuda"
  fi
fi

title "后端 Python 依赖"

if "$VENV_PYTHON" -c "import fastapi, sqlalchemy, jose, passlib" 2>/dev/null; then
  skip "核心库已安装"
  report_add "skip" "后端 Python 依赖" "已安装"
else
  info "安装后端 Python 依赖..."
  "$VENV_PIP" install -r "$ROOT_DIR/requirements.txt" -q
  ok "后端 Python 依赖安装完成"
  report_add "ok" "后端 Python 依赖" "已安装"
fi

title "推理服务依赖 (llama-cpp-python)"

if "$VENV_PYTHON" -c "import llama_cpp" 2>/dev/null; then
  skip "llama-cpp-python 已安装"
  report_add "skip" "llama-cpp-python" "已安装"
else
  info "编译安装 llama-cpp-python (可能需要几分钟)..."
  if [[ "$PLATFORM" == "mps" ]]; then
    CMAKE_ARGS="-DGGML_METAL=on" "$VENV_PIP" install -r "$ROOT_DIR/zhishitong/inference_server/requirements.txt" -q 2>&1 | tail -3
  elif [[ "$PLATFORM" == "cuda" ]]; then
    CMAKE_ARGS="-DGGML_CUDA=on" "$VENV_PIP" install -r "$ROOT_DIR/zhishitong/inference_server/requirements.txt" -q 2>&1 | tail -3
  else
    "$VENV_PIP" install -r "$ROOT_DIR/zhishitong/inference_server/requirements.txt" -q 2>&1 | tail -3
  fi
  ok "llama-cpp-python 安装完成"
  report_add "ok" "llama-cpp-python" "已安装 ($PLATFORM)"
fi

title "训练依赖 (PyTorch / Transformers / PEFT)"

TORCH_OK=false
if "$VENV_PYTHON" -c "import torch, transformers, peft" 2>/dev/null; then
  skip "PyTorch/Transformers/PEFT 已安装"
  TORCH_OK=true
  report_add "skip" "PyTorch & Transformers" "已安装"
elif [[ "$CAN_TRAIN" != "true" ]]; then
  warn "本机不满足训练条件，跳过 PyTorch 安装"
  report_add "skip" "PyTorch & Transformers" "本机不满足训练条件，跳过安装"
else
  info "安装训练依赖 (torch, transformers, peft)..."
  "$VENV_PIP" install -r "$ROOT_DIR/training/train_requirements.txt" -q 2>&1 | tail -3
  if "$VENV_PYTHON" -c "import torch" 2>/dev/null; then
    ok "训练依赖安装完成"
    TORCH_OK=true
    report_add "ok" "PyTorch & Transformers" "已安装"
  else
    warn "训练依赖安装失败（不影响后端运行）"
    report_add "warn" "PyTorch & Transformers" "安装失败"
  fi
fi

# ============================================================
#  5. 模型下载
# ============================================================
title "模型下载 (Qwen3-4B)"

MODELS_DIR="$ROOT_DIR/models"
mkdir -p "$MODELS_DIR"

if [ -f "$MODELS_DIR/qwen3-4b.gguf" ]; then
  MB=$(du -m "$MODELS_DIR/qwen3-4b.gguf" 2>/dev/null | cut -f1)
  ok "GGUF 模型已存在 ($MB MB)"
  report_add "ok" "Qwen3-4B GGUF 模型" "已存在 (${MB}MB)"
elif [[ "$CAN_DOWNLOAD" != "true" ]]; then
  warn "本机不满足模型运行条件 (RAM: ${RAM_GB}GB, Disk: ${DISK_GB}GB)，跳过下载"
  report_add "skip" "Qwen3-4B GGUF 模型" "跳过: 本机不满足最低要求"
else
  info "准备下载模型 (约 2.5 GB)..."
  if "$VENV_PYTHON" -c "import huggingface_hub" 2>/dev/null; then
    PIP_HF=-q
  else
    info "安装 huggingface_hub..."
    "$VENV_PIP" install huggingface_hub -q
    PIP_HF=-q
  fi
  if "$VENV_PYTHON" "$ROOT_DIR/setup/_download_model.py" --download --models-dir "$MODELS_DIR" 2>&1; then
    ok "模型下载完成"
    report_add "ok" "Qwen3-4B GGUF 模型" "已下载"
  else
    warn "模型下载失败"
    report_add "warn" "Qwen3-4B GGUF 模型" "下载失败"
  fi
fi

# ============================================================
#  6. 前端依赖
# ============================================================
title "前端 npm 依赖"

FRONTEND_DIR="$ROOT_DIR/zhishitong/frontend"
if [ -d "$FRONTEND_DIR/node_modules" ]; then
  NPKGS=$(ls -1 "$FRONTEND_DIR/node_modules" 2>/dev/null | wc -l | tr -d ' ')
  skip "node_modules 已存在 ($NPKGS 个包)"
  report_add "skip" "前端 node_modules" "已存在 ($NPKGS 个包)"
else
  info "安装 npm 依赖..."
  npm --prefix "$FRONTEND_DIR" install 2>&1 | tail -3
  ok "npm 依赖安装完成"
  report_add "ok" "前端 node_modules" "已安装"
fi

# ============================================================
#  7. 数据库初始化
# ============================================================
title "数据库初始化"

DB_PATH="$ROOT_DIR/zhishitong/backend/data"
mkdir -p "$DB_PATH"

if PYTHONPATH="$ROOT_DIR/zhishitong/backend" "$VENV_PYTHON" "$ROOT_DIR/zhishitong/backend/seed.py" 2>&1; then
  ok "数据库初始化完成"
  report_add "ok" "数据库 & 种子数据" "已初始化"
else
  warn "数据库初始化异常（不影响已存在的数据）"
  report_add "warn" "数据库 & 种子数据" "初始化异常"
fi

# ============================================================
#  8. 汇总报告
# ============================================================
title "安装报告"

# 列宽
MAX_TITLE=30
fmt="  %-4s %-${MAX_TITLE}s %s\n"

for entry in "${R_ITEMS[@]}"; do
  IFS='|' read -r st ti de <<< "$entry"
  case "$st" in
    ok)    icon="${GREEN}✓${NC}" ;;
    skip)  icon="${YELLOW}─${NC}" ;;
    warn)  icon="${YELLOW}!${NC}" ;;
    err)   icon="${RED}✗${NC}" ;;
    *)     icon="  " ;;
  esac
  printf "$fmt" "$icon" "$ti" "$de"
done

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "  ${BOLD}摘要${NC}"
echo -e "${CYAN}───────────────────────────────────────────────────────────────${NC}"

OK_CNT=0; TOTAL_CNT=${#R_ITEMS[@]}
for entry in "${R_ITEMS[@]}"; do
  [[ "${entry%%|*}" != "err" && "${entry%%|*}" != "warn" ]] && ((OK_CNT++))
done
echo -e "  已完成 ${GREEN}${OK_CNT}${NC} / ${TOTAL_CNT} 项"

if [[ "$CAN_DOWNLOAD" != "true" && "$CAN_INFER" != "true" ]]; then
  echo -e "  ${YELLOW}⚠  本机不满足本地推理条件${NC}"
  echo "    内存 ${RAM_GB}GB < ${THRESHOLD_INFER}GB"
  echo "    推荐使用外部 LLM API (Pro 模式)，或跳过本地模型使用 start.sh"
elif [[ "$CAN_TRAIN" != "true" ]]; then
  echo -e "  ${YELLOW}⚠  本机可本地推理但 LoRA 训练可能受限${NC}"
  echo "    训练推荐 ≥ ${THRESHOLD_TRAIN_RAM}GB RAM + ${THRESHOLD_VRAM_TRAIN}GB VRAM (有 GPU) 或 ${THRESHOLD_TRAIN_CPU}GB RAM (纯 CPU)"
fi

echo ""
echo -e "  ${BOLD}启动开发服务器:${NC}"
echo "    cd zhishitong && bash start.sh"
echo ""
echo -e "  ${BOLD}训练 LoRA (可选):${NC}"
echo "    source .venv/bin/activate"
echo "    python training/train_lora.py"
echo ""
echo -e "  ${BOLD}运行测试:${NC}"
echo "    source .venv/bin/activate"
echo "    PYTHONPATH=zhishitong/backend python -m unittest discover -s zhishitong/backend/tests"
echo ""
