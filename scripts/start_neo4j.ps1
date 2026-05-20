# 启动 Neo4j（后台 Java 进程）
$root = Split-Path $PSScriptRoot -Parent
$envPs1 = Join-Path $root "tools\neo4j.env.ps1"
if (-not (Test-Path $envPs1)) {
    Write-Error "Run scripts\install_neo4j.ps1 first"
    exit 1
}
. $envPs1

if ((Test-NetConnection localhost -Port 7687 -WarningAction SilentlyContinue).TcpTestSucceeded) {
    Write-Host "Neo4j already running: bolt://localhost:7687" -ForegroundColor Green
    exit 0
}

$neo4jBat = Join-Path $env:NEO4J_HOME "bin\neo4j.bat"
$logDir = Join-Path $root "data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logOut = Join-Path $logDir "neo4j-stdout.log"
$logErr = Join-Path $logDir "neo4j-stderr.log"

Write-Host "Starting Neo4j at $env:NEO4J_HOME ..."
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$neo4jBat`" console" `
    -WorkingDirectory $env:NEO4J_HOME `
    -WindowStyle Hidden `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError $logErr

$ready = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    if ((Test-NetConnection localhost -Port 7687 -WarningAction SilentlyContinue).TcpTestSucceeded) {
        $ready = $true
        break
    }
    if ($i % 10 -eq 9) { Write-Host "  waiting... ($($i+1)*2 s)" }
}

if ($ready) {
    Write-Host "Neo4j ready: bolt://localhost:7687  http://localhost:7474" -ForegroundColor Green
} else {
    Write-Host "Neo4j not ready yet. Logs:" -ForegroundColor Yellow
    Write-Host "  $logOut"
    Write-Host "  $logErr"
    if (Test-Path $logErr) { Get-Content $logErr -Tail 20 }
}
