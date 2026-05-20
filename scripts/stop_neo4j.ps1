$root = Split-Path $PSScriptRoot -Parent
$envPs1 = Join-Path $root "tools\neo4j.env.ps1"
if (Test-Path $envPs1) { . $envPs1 }
$neo4jBat = Join-Path $env:NEO4J_HOME "bin\neo4j.bat"
& $neo4jBat stop 2>$null
Get-Process -Name "java" -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*neo4j*"
} | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "Neo4j stopped."
