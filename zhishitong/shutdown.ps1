<#
.SYNOPSIS
  智审通 — Windows 一键停止脚本
  停止 start.ps1 启动的所有服务
  用法:  cd zhishitong && powershell -File shutdown.ps1
#>

$ROOT_DIR = Split-Path -Parent $PSCommandPath

function Write-Log  ($m) { Write-Host "✓ $m" -ForegroundColor Green }
function Write-Warn ($m) { Write-Host "! $m" -ForegroundColor Yellow }
function Write-Err  ($m) { Write-Host "✗ $m" -ForegroundColor Red }

# ── 按端口号查找进程并终止 ──
function Stop-ByPort {
    param($Port, $Name)
    try {
        $conn = netstat -ano | Select-String "LISTENING" | Select-String ":$Port\s"
        if (-not $conn) { Write-Warn "$Name 未运行 (端口 $Port)"; return }

        $pids = $conn | ForEach-Object {
            $_.Line -match '(\d+)$' | Out-Null
            if ($matches) { [int]$matches[1] }
        } | Select-Object -Unique

        foreach ($pid in $pids) {
            try {
                $proc = Get-Process -Id $pid -ErrorAction Stop
                Stop-Process -Id $pid -Force -ErrorAction Stop
                Write-Log "$Name (pid $pid) 已停止"
            } catch { Write-Warn "$Name (pid $pid) 停止失败: $_" }
        }
    } catch { Write-Warn "查找端口 $Port 失败: $_" }
}

# ── 按进程名查找并终止（兜底） ──
function Stop-ByName {
    param($Pattern, $Name)
    try {
        $procs = Get-Process | Where-Object { $_.CommandLine -match $Pattern }
        foreach ($proc in $procs) {
            try {
                Stop-Process -Id $proc.Id -Force -ErrorAction Stop
                Write-Log "$Name (pid $($proc.Id)) 已停止"
            } catch { Write-Warn "$Name (pid $($proc.Id)) 停止失败: $_" }
        }
    } catch { }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  智审通 — 正在停止所有服务" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 优先按本项目路径停止 ──
Stop-ByName "server:app"      "推理服务 (本项目)"
Stop-ByName "main:app"        "后端 (本项目)"
Stop-ByName "vite"            "前端 (本项目)"

# ── 2. 按端口兜底 ──
Stop-ByPort 18080 "推理服务 (端口 18080)"
Stop-ByPort 8080  "后端 (端口 8080)"
Stop-ByPort 5173  "前端 (端口 5173)"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ✅ 所有服务已停止" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
