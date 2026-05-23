# 使用项目虚拟环境 (Python 3.12) 运行命令
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "正在创建虚拟环境 (Python 3.12)..."
    py -3.12 -m venv (Join-Path $Root ".venv")
    & (Join-Path $Root ".venv\Scripts\pip.exe") install -r (Join-Path $Root "requirements.txt")
    & (Join-Path $Root ".venv\Scripts\pip.exe") install sentence-transformers
}

$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
Set-Location $Root

if ($args.Count -eq 0) {
    & $Python scripts/run_server.py
} else {
    & $Python @args
}
