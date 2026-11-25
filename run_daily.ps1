# 작업 스케줄러가 매일 실행하는 스크립트.
# 1) 새 댓글 수집 → 읽기·작성·검수 → 승인 대기열에 쌓기
# 2) 이미 review 에서 승인해 둔 답글만 게시 (승인 안 한 초안은 게시되지 않음)
# 기록: data\logs\YYYY-MM-DD.log
param([string]$Config = "config.youtube.toml")

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# 작업 스케줄러 환경에서도 사용자 환경변수의 API 키를 확실히 읽는다
if (-not $env:ANTHROPIC_API_KEY) {
    $env:ANTHROPIC_API_KEY = [Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY", "User")
}
$env:AUTOREPLY_UNATTENDED = "1"
$env:PYTHONIOENCODING = "utf-8"

$logDir = Join-Path $PSScriptRoot "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ((Get-Date -Format "yyyy-MM-dd") + ".log")

foreach ($cmd in @("run", "post", "status")) {
    $stamp = Get-Date -Format "HH:mm:ss"
    cmd /c "echo ===== $stamp $cmd ===== >> `"$log`""
    cmd /c "python -u main.py $cmd --config `"$Config`" >> `"$log`" 2>&1"
}
