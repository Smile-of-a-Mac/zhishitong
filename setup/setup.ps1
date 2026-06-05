<#
.SYNOPSIS
  智审通 · Windows 快速安装脚本 (PowerShell 5.1+ / PowerShell 7+)
  功能：预检 → 按需安装 → 汇总报告
  用法:  .\setup\setup.ps1
#>

$ErrorActionPreference = "Stop"
$ROOT_DIR = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$VENV_DIR = Join-Path $ROOT_DIR ".venv"
$VENV_PYTHON = Join-Path $VENV_DIR "Scripts\python.exe"
$VENV_PIP = Join-Path $VENV_DIR "Scripts\pip.exe"

# ---------- 报告 ----------
$global:Report = @()

function Add-Report($status, $item, $detail) {
    $global:Report += [PSCustomObject]@{ Status = $status; Item = $item; Detail = $detail }
}

function Write-OK($msg)  { Write-Host "  ✓  $msg" -ForegroundColor Green }
function Write-Skip($msg){ Write-Host "  ⊘  $msg" -ForegroundColor DarkGray }
function Write-Warn($msg){ Write-Host "  ─  $msg" -ForegroundColor Yellow }
function Write-Fail($msg){ Write-Host "  ✗  $msg" -ForegroundColor Red; exit 1 }
function Write-Info($msg){ Write-Host "  i  $msg" -ForegroundColor Cyan }
function Write-Title($m) { Write-Host "`n━━━ $m ━━━" -ForegroundColor Cyan }

# ============================================================
#  1. 前置检查
# ============================================================
Write-Host @"

  智审通  —  一键环境安装
  $ROOT_DIR
"@

Write-Title "前置检查"

# Python
$pyFound = $false; $pyVer = ""
foreach ($cmd in @("python3", "python")) {
    try {
        $v = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($v -and [version]$v -ge [version]"3.10") {
            $global:PY = $cmd
            $pyVer = & $cmd --version 2>&1
            $pyFound = $true; break
        }
    } catch {}
}
if (-not $pyFound) {
    Write-Warn "Python 3.10+ 未找到"
    Add-Report "err" "Python 3.10+" "未安装"
    Write-Fail "请从 https://www.python.org/downloads/ 下载安装"
}
Write-OK "Python: $pyVer"
Add-Report "ok" "Python 3.10+" "$pyVer"

# Node.js
try {
    $nv = node --version 2>$null
    Write-OK "Node.js: $nv"
    Add-Report "ok" "Node.js 18+" "$nv"
} catch {
    Add-Report "err" "Node.js 18+" "未安装"
    Write-Fail "请从 https://nodejs.org/ 下载安装"
}

# Git
try {
    $gv = git --version 2>$null
    Write-OK "Git: $gv"
    Add-Report "ok" "Git" "$gv"
} catch {
    Write-Warn "Git 未找到"
    Add-Report "warn" "Git" "未安装（部分功能受限）"
}

# ============================================================
#  2. 系统能力检测
# ============================================================
Write-Title "系统能力检测"

$arch = if ($env:PROCESSOR_ARCHITECTURE) { $env:PROCESSOR_ARCHITECTURE } else { "未知" }
Write-OK "系统: Windows $arch"

$totalRamGB = 0.0
try {
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $totalRamGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    Write-OK "内存: ${totalRamGB}GB"
} catch {
    Write-Warn "无法检测内存"
}

try {
    $drive = (Get-Item $ROOT_DIR).PSDrive
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    Write-OK "空闲磁盘: ~${freeGB}GB"
} catch { $freeGB = 0 }

# GPU & VRAM
$gpu = ""; $vramGB = 0.0
try {
    $gpuLine = nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null
    if ($gpuLine) {
        $parts = $gpuLine[0] -split ', '
        $gpu = "NVIDIA $($parts[0])"
        $vramStr = $parts[1] -replace '[^0-9.]',''
        [double]::TryParse($vramStr, [ref]$vramGB) | Out-Null
        $vramGB = [math]::Round($vramGB / 1024, 1)
    }
} catch {}
if ($gpu) { Write-OK "GPU: $gpu (VRAM: ${vramGB}GB)" }
else { Write-Warn "未检测到 GPU，推理/训练将使用 CPU" }

$thInfer = 4.0; $thTrainCpu = 12.0; $thTrainRam = 8.0
$thVramTrain = 6.0; $thVramInfer = 3.0; $thDisk = 8.0
$canInfer = $false; $canTrain = $false; $canDownload = $false

if ($totalRamGB -ge $thInfer) { $canInfer = $true }

# Training check with VRAM
if ($gpu) {
    if ($vramGB -ge $thVramTrain -and $totalRamGB -ge $thTrainRam) {
        $canTrain = $true
        $trainReason = "VRAM ${vramGB}GB ≥ ${thVramTrain}GB, RAM ${totalRamGB}GB ≥ ${thTrainRam}GB"
    } else {
        $trainReason = "VRAM ${vramGB}GB < ${thVramTrain}GB 或 RAM ${totalRamGB}GB < ${thTrainRam}GB"
    }
} elseif ($totalRamGB -ge $thTrainCpu) {
    $canTrain = $true
    $trainReason = "RAM ${totalRamGB}GB ≥ ${thTrainCpu}GB (纯 CPU)"
} else {
    $trainReason = "RAM ${totalRamGB}GB < ${thTrainCpu}GB"
}

if ($canInfer) {
    if ($gpu -and $vramGB -ge $thVramInfer) { Add-Report "ok" "本地推理" "可运行 (VRAM ${vramGB}GB, RAM ${totalRamGB}GB)" }
    else { Add-Report "ok" "本地推理" "可运行 (RAM ${totalRamGB}GB, CPU)" }
} else { Add-Report "skip" "本地推理" "内存不足 (${totalRamGB}GB < ${thInfer}GB)" }

if ($canTrain) { Add-Report "ok" "LoRA 训练" "可运行 ($trainReason)" }
else { Add-Report "skip" "LoRA 训练" "$trainReason" }

if ($canInfer -and $freeGB -ge $thDisk) { $canDownload = $true }

if (-not $canInfer) {
    Write-Warn "  ⚠ 本机内存不足，无法运行本地推理和 LoRA 训练"
    Write-Warn "    推荐使用外部 LLM API (Pro 模式) 或升级硬件"
}

# ============================================================
#  3. Python 环境
# ============================================================
Write-Title "Python 环境"

if (Test-Path $VENV_DIR) {
    Write-Skip "虚拟环境已存在: $VENV_DIR"
    Add-Report "skip" "Python 虚拟环境" "已存在"
} else {
    Write-Info "创建虚拟环境..."
    & $global:PY -m venv $VENV_DIR
    Write-OK "虚拟环境已创建"
    Add-Report "ok" "Python 虚拟环境" "新建"
}

& $VENV_PYTHON -m pip install --upgrade pip setuptools wheel -q

# ============================================================
#  4. Python 依赖
# ============================================================
Write-Title "后端 Python 依赖"
try {
    & $VENV_PYTHON -c "import fastapi, sqlalchemy, jose, passlib" 2>$null
    Write-Skip "核心库已安装"
    Add-Report "skip" "后端 Python 依赖" "已安装"
} catch {
    Write-Info "安装后端 Python 依赖..."
    & $VENV_PIP install -r (Join-Path $ROOT_DIR "requirements.txt") -q
    Write-OK "后端 Python 依赖安装完成"
    Add-Report "ok" "后端 Python 依赖" "已安装"
}

Write-Title "推理服务依赖 (llama-cpp-python)"
try {
    & $VENV_PYTHON -c "import llama_cpp" 2>$null
    Write-Skip "llama-cpp-python 已安装"
    Add-Report "skip" "llama-cpp-python" "已安装"
} catch {
    Write-Info "安装 llama-cpp-python..."
    if ($gpu) { $env:CMAKE_ARGS = "-DGGML_CUDA=on" }
    & $VENV_PIP install -r (Join-Path $ROOT_DIR "zhishitong\inference_server\requirements.txt") -q 2>&1 | Select-Object -Last 3
    Write-OK "llama-cpp-python 安装完成"
    Add-Report "ok" "llama-cpp-python" "已安装"
}

Write-Title "训练依赖 (PyTorch / Transformers / PEFT)"
try {
    & $VENV_PYTHON -c "import torch, transformers, peft" 2>$null
    Write-Skip "PyTorch/Transformers/PEFT 已安装"
    Add-Report "skip" "PyTorch & Transformers" "已安装"
} catch {
    if (-not $canTrain) {
        Write-Warn "本机不满足训练条件，跳过安装"
        Add-Report "skip" "PyTorch & Transformers" "本机不满足训练条件，跳过安装"
    } else {
        Write-Info "安装训练依赖..."
        & $VENV_PIP install -r (Join-Path $ROOT_DIR "training\train_requirements.txt") -q
        Write-OK "训练依赖安装完成"
        Add-Report "ok" "PyTorch & Transformers" "已安装"
    }
}

# ============================================================
#  5. 模型下载
# ============================================================
Write-Title "模型下载 (Qwen3-4B)"

$modelsDir = Join-Path $ROOT_DIR "models"
New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null

$ggufDest = Join-Path $modelsDir "qwen3-4b.gguf"
if (Test-Path $ggufDest) {
    $mb = [math]::Round((Get-Item $ggufDest).Length / 1MB, 0)
    Write-OK "GGUF 模型已存在 ($mb MB)"
    Add-Report "ok" "Qwen3-4B GGUF 模型" "已存在 (${mb}MB)"
} elseif (-not $canDownload) {
    Write-Warn "本机不满足模型运行条件，跳过下载"
    Add-Report "skip" "Qwen3-4B GGUF 模型" "跳过: 本机不满足最低要求"
} else {
    Write-Info "准备下载模型 (约 2.5 GB)..."
    try { & $VENV_PYTHON -c "import huggingface_hub" 2>$null }
    catch { & $VENV_PIP install huggingface_hub -q }
    & $VENV_PYTHON (Join-Path $ROOT_DIR "setup\_download_model.py") --download --models-dir $modelsDir 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "模型下载完成"
        Add-Report "ok" "Qwen3-4B GGUF 模型" "已下载"
    } else {
        Write-Warn "模型下载失败"
        Add-Report "warn" "Qwen3-4B GGUF 模型" "下载失败"
    }
}

# ============================================================
#  6. 前端依赖
# ============================================================
Write-Title "前端 npm 依赖"
$feDir = Join-Path $ROOT_DIR "zhishitong\frontend"
if (Test-Path (Join-Path $feDir "node_modules")) {
    Write-Skip "node_modules 已存在"
    Add-Report "skip" "前端 node_modules" "已存在"
} else {
    Push-Location $feDir
    try {
        Write-Info "安装 npm 依赖..."
        npm install 2>&1 | Select-Object -Last 3
        Write-OK "npm 依赖安装完成"
        Add-Report "ok" "前端 node_modules" "已安装"
    } finally { Pop-Location }
}

# ============================================================
#  7. 数据库初始化
# ============================================================
Write-Title "数据库初始化"
$env:PYTHONPATH = Join-Path $ROOT_DIR "zhishitong\backend"
try {
    & $VENV_PYTHON (Join-Path $ROOT_DIR "zhishitong\backend\seed.py") 2>&1
    Write-OK "数据库初始化完成"
    Add-Report "ok" "数据库 & 种子数据" "已初始化"
} catch {
    Write-Warn "数据库初始化异常（不影响已有数据）: $_"
    Add-Report "warn" "数据库 & 种子数据" "初始化异常"
}

# ============================================================
#  8. 汇总报告
# ============================================================
Write-Title "安装报告"

foreach ($r in $global:Report) {
    $icon = switch ($r.Status) {
        "ok"   { "✓"  }
        "skip" { "─"  }
        "warn" { "!"  }
        "err"  { "✗"  }
        default { " " }
    }
    $color = switch ($r.Status) {
        "ok"   { "Green"  }
        "skip" { "DarkGray" }
        "warn" { "Yellow" }
        "err"  { "Red"    }
        default { "White" }
    }
    Write-Host "  $icon  $($r.Item)" -NoNewline -ForegroundColor $color
    $pad = " " * [math]::Max(1, 30 - $r.Item.Length)
    Write-Host "$pad $($r.Detail)" -ForegroundColor $color
}

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  摘要" -ForegroundColor Cyan
$okCount = ($global:Report | Where-Object { $_.Status -in @("ok","skip") }).Count
Write-Host "  已完成 $okCount / $($global:Report.Count) 项"

if (-not $canInfer) {
    Write-Host "  ⚠  本机不满足本地推理条件 (RAM ${totalRamGB}GB < ${thInfer}GB)"
    Write-Host "    推荐使用外部 LLM API (Pro 模式)"
}
Write-Host ""
Write-Host "  启动开发服务器（一键）:" -ForegroundColor White
Write-Host "    cd zhishitong"
Write-Host "    powershell -File start.ps1"
Write-Host ""
Write-Host "  或分步启动:" -ForegroundColor White
Write-Host "    cd zhishitong"
Write-Host "    ..\.venv\Scripts\uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload"
Write-Host "    # 另一个终端:"
Write-Host "    ..\.venv\Scripts\uvicorn inference_server.server:app --host 0.0.0.0 --port 18080"
Write-Host ""
Write-Host "  运行测试:" -ForegroundColor White
Write-Host "    .venv\Scripts\activate"
