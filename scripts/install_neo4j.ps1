# 无 Docker 安装 Neo4j Community（ZIP + JDK）
# 用法: powershell -ExecutionPolicy Bypass -File scripts\install_neo4j.ps1

param(
    [string]$Neo4jVersion = "5.26.0",
    [string]$Password = "filekg123",
    [switch]$InstallService
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$toolsDir = Join-Path $root "tools"
$neo4jHome = Join-Path $toolsDir "neo4j-community-$Neo4jVersion"
$zipPath = Join-Path $toolsDir "neo4j-community-$Neo4jVersion-windows.zip"
$zipUrl = "https://dist.neo4j.org/neo4j-community-$Neo4jVersion-windows.zip"

Write-Host "=== Neo4j Community Installer (no Docker) ===" -ForegroundColor Cyan

# Java
$java = Get-Command java -ErrorAction SilentlyContinue
if (-not $java) {
    Write-Host "Java not found. Installing Temurin 17..."
    winget install EclipseAdoptium.Temurin.17.JDK --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
}
java -version

New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

if (-not (Test-Path $neo4jHome)) {
    if (-not (Test-Path $zipPath)) {
        Write-Host "Downloading Neo4j $Neo4jVersion ..."
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    }
    Write-Host "Extracting to $toolsDir ..."
    Expand-Archive -Path $zipPath -DestinationPath $toolsDir -Force
    $extracted = Get-ChildItem $toolsDir -Directory | Where-Object { $_.Name -like "neo4j-community*" } | Select-Object -First 1
    if ($extracted.FullName -ne $neo4jHome -and (Test-Path $extracted.FullName)) {
        if (Test-Path $neo4jHome) { Remove-Item $neo4jHome -Recurse -Force }
        Rename-Item $extracted.FullName $neo4jHome
    }
}

$neo4jBin = Join-Path $neo4jHome "bin"
$neo4jAdmin = Join-Path $neo4jBin "neo4j-admin.bat"
$neo4jBat = Join-Path $neo4jBin "neo4j.bat"

if (-not (Test-Path $neo4jAdmin)) {
    throw "Neo4j not found at $neo4jHome"
}

# 初始密码（仅首次）
$dataDir = Join-Path $neo4jHome "data\databases"
if (-not (Test-Path $dataDir)) {
    Write-Host "Setting initial password..."
    & $neo4jAdmin dbms set-initial-password $Password
}

# 写入环境文件供其他脚本使用
$envFile = Join-Path $root "tools\neo4j.env.ps1"
@"
`$env:NEO4J_HOME = "$neo4jHome"
`$env:Path = "$neo4jBin;" + `$env:Path
"@ | Set-Content $envFile -Encoding UTF8

# 更新项目 .env
$dotenv = Join-Path $root ".env"
$content = Get-Content $dotenv -Raw -ErrorAction SilentlyContinue
if ($content -match "FILEKG_GRAPH_BACKEND=local") {
    $content = $content -replace "FILEKG_GRAPH_BACKEND=local", "FILEKG_GRAPH_BACKEND=neo4j"
} elseif ($content -notmatch "FILEKG_GRAPH_BACKEND=") {
    $content += "`nFILEKG_GRAPH_BACKEND=neo4j`n"
}
$content = $content -replace "NEO4J_PASSWORD=.*", "NEO4J_PASSWORD=$Password"
Set-Content $dotenv $content.TrimEnd() -Encoding UTF8

Write-Host "NEO4J_HOME=$neo4jHome" -ForegroundColor Green
Write-Host "Updated .env -> FILEKG_GRAPH_BACKEND=neo4j" -ForegroundColor Green

if ($InstallService) {
    Write-Host "Installing Windows service (requires Admin)..."
    Start-Process -FilePath $neo4jBat -ArgumentList "install-service" -Verb RunAs -Wait
    Start-Process -FilePath $neo4jBat -ArgumentList "start" -Verb RunAs -Wait
} else {
    Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  .\scripts\start_neo4j.ps1"
Write-Host "  .\.venv\Scripts\python.exe scripts\set_neo4j_password.py   # first time only"
}
