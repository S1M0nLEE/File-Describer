# 一键：创建环境 → 下载模型 → 生成数据 → 建索引 → 调试
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host ">>> 创建 Python 3.12 虚拟环境..."
    py -3.12 -m venv (Join-Path $Root ".venv")
    & (Join-Path $Root ".venv\Scripts\pip.exe") install -r requirements.txt
}

Write-Host ">>> 验证嵌入模型..."
& $Py scripts/setup_models.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ">>> 生成示例数据集..."
& $Py scripts/generate_dataset.py

Write-Host ">>> 建立索引..."
& $Py scripts/index_directory.py data/dataset --clear

Write-Host ">>> 端到端检索测试..."
& $Py scripts/debug_pipeline.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "全部完成。启动服务: .\scripts\run.ps1"
Write-Host "浏览器: http://localhost:8765"
