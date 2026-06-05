<#
.SYNOPSIS
  智审通 — Windows 一键启动脚本 (PowerShell 5.1+)
  自动完成：安装依赖 → 初始化数据 → 启动推理服务 → 启动前后端
  用法:  cd zhishitong && powershell -File start.ps1
#>

$ErrorActionPreference = "Stop"

$ROOT_DIR      = Split-Path -Parent $PSCommandPath
$BACKEND_DIR   = Join-Path $ROOT_DIR "backend"
$FRONTEND_DIR  = Join-Path $ROOT_DIR "frontend"
$INFER_DIR     = Join-Path $ROOT_DIR "inference_server"
$VENV_DIR      = Join-Path (Split-Path -Parent $ROOT_DIR) ".venv"
$VENV_PYTHON   = Join-Path $VENV_DIR "Scripts\python.exe"
$VENV_UVICORN  = Join-Path $VENV_DIR "Scripts\uvicorn.exe"
$VENV_PIP      = Join-Path $VENV_DIR "Scripts\pip.exe"

# ---------- 全局进程跟踪 ----------
$script:Processes = @{}  # name -> System.Diagnostics.Process

# ---------- 颜色输出 ----------
function Write-Log  ($m) { Write-Host "✓ $m" -ForegroundColor Green }
function Write-Warn ($m) { Write-Host "! $m" -ForegroundColor Yellow }
function Write-Err  ($m) { Write-Host "✗ $m" -ForegroundColor Red }

function Run-Step {
    param($Label, [ScriptBlock]$Block)
    Write-Log $Label
    try { & $Block }
    catch { Write-Err "$Label 失败: $_"; exit 1 }
}

# ---------- 前置检查 ----------
if (-not (Test-Path $BACKEND_DIR))  { Write-Err "未找到后端目录: $BACKEND_DIR"; exit 1 }
if (-not (Test-Path $FRONTEND_DIR)) { Write-Err "未找到前端目录: $FRONTEND_DIR"; exit 1 }
if (-not (Test-Path $INFER_DIR))    { Write-Err "未找到推理服务目录: $INFER_DIR"; exit 1 }
if (-not (Test-Path $VENV_PYTHON))  { Write-Err "未找到虚拟环境 Python: $VENV_PYTHON"; exit 1 }

try { $nv = node --version } catch { Write-Err "未检测到 Node.js，请先安装"; exit 1 }

# ---------- JWT 密钥持久化 ----------
$JWT_SECRET_FILE = Join-Path $BACKEND_DIR "data\.jwt_secret"
if (Test-Path $JWT_SECRET_FILE) {
    $env:JWT_SECRET = (Get-Content $JWT_SECRET_FILE -Raw).Trim()
    Write-Log "JWT_SECRET 已从 $JWT_SECRET_FILE 加载"
} else {
    $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $JWT_SECRET_FILE)
    $env:JWT_SECRET = & $VENV_PYTHON -c "import secrets; print(secrets.token_urlsafe(48))"
    Set-Content -Path $JWT_SECRET_FILE -Value $env:JWT_SECRET
    Write-Log "JWT_SECRET 已自动生成并持久化到 $JWT_SECRET_FILE"
}

# ---------- 1. 后端依赖 ----------
try { & $VENV_PYTHON -c "import fastapi, sqlalchemy, jose, passlib" 2>$null; Write-Log "后端 Python 依赖已就绪" }
catch { Run-Step "安装后端 Python 依赖" { & $VENV_PIP install -r (Join-Path $ROOT_DIR "..\requirements.txt") -q } }

# ---------- 2. 推理服务依赖 ----------
try { & $VENV_PYTHON -c "import llama_cpp" 2>$null; Write-Log "推理服务依赖已就绪" }
catch { Run-Step "安装推理服务依赖" { & $VENV_PIP install -r (Join-Path $INFER_DIR "requirements.txt") -q } }

# ---------- 3. 数据库初始化 ----------
Write-Log "初始化数据库 & 种子数据…"
$env:PYTHONPATH = $BACKEND_DIR
& $VENV_PYTHON (Join-Path $BACKEND_DIR "seed.py") 2>&1

# ---------- 4. 前端依赖 ----------
$feNodeModules = Join-Path $FRONTEND_DIR "node_modules"
if (Test-Path $feNodeModules) { Write-Log "前端 node_modules 已存在" }
else { Run-Step "安装前端 npm 依赖" { & npm --prefix $FRONTEND_DIR install } }

# ---------- 清理函数 ----------
function Stop-AllServices {
    param([int]$ExitCode = 0)
    Write-Host ""
    Write-Warn "正在停止服务…"
    foreach ($name in $script:Processes.Keys) {
        $proc = $script:Processes[$name]
        if ($proc -and !$proc.HasExited) {
            try { $proc.Kill(); Write-Log "$name 已停止" }
            catch { Write-Warn "$name 停止失败: $_" }
        }
    }
    if ($ExitCode -ne 0) { exit $ExitCode }
}

# ---------- 5. 切换微调模型 ----------
$modelsDir = Join-Path (Split-Path -Parent $ROOT_DIR) "models"
$loraGGUF  = Join-Path $modelsDir "qwen3-14b-lora.gguf"
if (Test-Path $loraGGUF) {
    $env:MODEL_PATH = $loraGGUF
    Write-Log "使用微调模型: qwen3-14b-lora.gguf"
}

# ---------- 6. 启动推理服务 ----------
Write-Log "启动本地推理服务 (llama.cpp)…"
$env:MODEL_PATH = if ($env:MODEL_PATH) { $env:MODEL_PATH } else { Join-Path $modelsDir "qwen3-14b-lora.gguf" }
$null = New-Item -ItemType Directory -Force -Path (Join-Path $ROOT_DIR "logs")

$inferProc = Start-Process -FilePath $VENV_UVICORN -NoNewWindow -PassThru -ArgumentList @(
    "server:app",
    "--host", "0.0.0.0",
    "--port", "18080"
) -RedirectStandardOutput (Join-Path $ROOT_DIR "logs\inference.log") -RedirectStandardError (Join-Path $ROOT_DIR "logs\inference.log")
$script:Processes["推理服务"] = $inferProc

$inferReady = $false
for ($i = 0; $i -lt 60; $i++) {
    try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:18080/health" -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { $inferReady = $true; break } } catch {}
    Start-Sleep -Seconds 2
}
if (-not $inferReady) { Write-Err "推理服务启动超时"; Stop-AllServices -ExitCode 1 }
Write-Log "推理服务就绪 → http://localhost:18080"

# ---------- 7. 启动后端 ----------
Write-Log "启动后端 (uvicorn)…"
$backendProc = Start-Process -FilePath $VENV_UVICORN -NoNewWindow -PassThru -ArgumentList @(
    "main:app",
    "--host", "0.0.0.0",
    "--port", "8080",
    "--reload"
) -RedirectStandardOutput (Join-Path $ROOT_DIR "logs\backend.log") -RedirectStandardError (Join-Path $ROOT_DIR "logs\backend.log")
$script:Processes["后端"] = $backendProc

$backendReady = $false
for ($i = 0; $i -lt 30; $i++) {
    try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/health" -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { $backendReady = $true; break } } catch {}
    Start-Sleep -Seconds 1
}
if (-not $backendReady) { Write-Err "后端启动超时"; Stop-AllServices -ExitCode 1 }
Write-Log "后端就绪 → http://localhost:8080"

# ---------- 8. 启动前端 ----------
Write-Log "启动前端 (vite dev server)…"
$frontendProc = Start-Process -FilePath "npx" -NoNewWindow -PassThru -ArgumentList @(
    "vite",
    "--host", "0.0.0.0",
    "--port", "5173"
) -WorkingDirectory $FRONTEND_DIR -RedirectStandardOutput (Join-Path $ROOT_DIR "logs\frontend.log") -RedirectStandardError (Join-Path $ROOT_DIR "logs\frontend.log")
$script:Processes["前端"] = $frontendProc

$frontendReady = $false
for ($i = 0; $i -lt 20; $i++) {
    try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { $frontendReady = $true; break } } catch {}
    Start-Sleep -Seconds 1
}
if (-not $frontendReady) { Write-Err "前端启动超时"; Stop-AllServices -ExitCode 1 }
Write-Log "前端就绪 → http://localhost:5173"

# ---------- 注册 Ctrl+C 处理 ----------
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -SupportEvent -Action { Stop-AllServices }
[Console]::CancelKeyPress | Out-Null

# ---------- 打印信息 ----------
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  智审通 — 开发环境已就绪" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  前端（推荐）:     http://localhost:5173" -ForegroundColor Cyan
Write-Host "  后端 API:         http://localhost:8080/api" -ForegroundColor Cyan
Write-Host "  API 文档:         http://localhost:8080/api/docs" -ForegroundColor Cyan
Write-Host "  本地推理服务:     http://localhost:18080" -ForegroundColor Cyan
Write-Host ""
Write-Host "  演示账号: admin、sdu_school_admin、sdu_dept_cs、sdu_finance_admin、sdu_student_a"
Write-Host ""
Write-Host "  按 Ctrl+C 同时停止所有服务" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan

# ---------- 等待所有子进程 ----------
while ($script:Processes.Values | Where-Object { -not $_.HasExited }) {
    Start-Sleep -Seconds 2
}
