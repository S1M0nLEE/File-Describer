# FileKG 一键配置：venv、依赖、预下载模型、索引、评估
param(
    [string]$Dataset = "code_dependency",
    [switch]$SkipEval,
    [switch]$FullIndex
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

Write-Host "=== FileKG Setup ===" -ForegroundColor Cyan

# 1. venv
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}
& $venvPy -m pip install --upgrade pip -q
Write-Host "Installing dependencies (may take several minutes)..."
& $venvPy -m pip install -r requirements.txt -q

# 2. load .env
. "$PSScriptRoot\load_env.ps1"

# 3. datasets
if (-not (Test-Path "data\datasets\$Dataset\annotations.json")) {
    Write-Host "Generating datasets..."
    & $venvPy scripts/create_datasets.py --dataset all
}

# 4. preload embedding model
Write-Host "Downloading embedding model BAAI/bge-small-zh-v1.5 ..."
& $venvPy -c @"
import os
os.environ.setdefault('FILEKG_GRAPH_BACKEND', 'local')
from src.config import get_config
from src.pipeline.embedder import Embedder
Embedder(get_config()).encode('warmup')
print('Embedding model ready.')
"@

# 5. index
$indexPath = if ($FullIndex) { "data\datasets\filekg_main" } else { "data\datasets\$Dataset" }
Write-Host "Indexing $indexPath (backend=$env:FILEKG_GRAPH_BACKEND)..."
& $venvPy scripts/run_indexing.py $indexPath

# 6. check
& "$PSScriptRoot\check_env.ps1"

# 7. evaluation
if (-not $SkipEval) {
    Write-Host "`nRunning evaluation on $Dataset ..."
    & $venvPy scripts/run_evaluation.py "data\datasets\$Dataset"
}

# Neo4j (optional, if install_neo4j was run)
if (Test-Path (Join-Path $root "tools\neo4j.env.ps1")) {
    $bolt = Test-NetConnection localhost -Port 7687 -WarningAction SilentlyContinue
    if (-not $bolt.TcpTestSucceeded) {
        Write-Host "Starting Neo4j..."
        & "$PSScriptRoot\start_neo4j.ps1"
        & $venvPy scripts\set_neo4j_password.py 2>$null
    }
}

Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host "Neo4j: .\scripts\start_neo4j.ps1  |  API: .\scripts\start_api.ps1"
Write-Host "After loading env: .\scripts\load_env.ps1"
