# 检查 FileKG 运行环境
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\load_env.ps1"
$root = Split-Path $PSScriptRoot -Parent

Write-Host "`n=== FileKG Environment Check ===" -ForegroundColor Cyan

# Python
$py = python --version 2>&1
Write-Host "Python: $py"

# Venv
$venv = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $venv) {
    Write-Host "Venv: OK ($venv)" -ForegroundColor Green
} else {
    Write-Host "Venv: missing (run scripts\setup.ps1)" -ForegroundColor Yellow
}

# Neo4j port
$neo = Test-NetConnection localhost -Port 7687 -WarningAction SilentlyContinue
if ($neo.TcpTestSucceeded) {
    Write-Host "Neo4j (7687): running" -ForegroundColor Green
    if ($env:FILEKG_GRAPH_BACKEND -eq "neo4j") {
        & (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $root "scripts\test_neo4j.py") 2>$null
    }
} else {
    Write-Host "Neo4j (7687): not running (backend=$env:FILEKG_GRAPH_BACKEND)" -ForegroundColor Yellow
    if (Test-Path (Join-Path $root "tools\neo4j.env.ps1")) {
        Write-Host "  Run: .\scripts\start_neo4j.ps1" -ForegroundColor Yellow
    }
}

# Ollama
$oll = Test-NetConnection localhost -Port 11434 -WarningAction SilentlyContinue
if ($oll.TcpTestSucceeded) {
    Write-Host "Ollama (11434): running" -ForegroundColor Green
} else {
    Write-Host "Ollama (11434): not running (optional)" -ForegroundColor DarkGray
}

# Data files
$cache = Join-Path $root "data\files_cache.json"
$graph = Join-Path $root "data\local_graph.json"
if (Test-Path $cache) { Write-Host "Index cache: OK" -ForegroundColor Green }
else { Write-Host "Index cache: not built yet" -ForegroundColor Yellow }
if (Test-Path $graph) { Write-Host "Local graph: OK" -ForegroundColor Green }

Write-Host "`nBackend: $env:FILEKG_GRAPH_BACKEND" -ForegroundColor Cyan
