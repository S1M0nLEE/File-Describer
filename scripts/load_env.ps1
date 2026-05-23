# 加载 .env 到当前 PowerShell 会话
$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if (-not (Test-Path $envFile)) {
    Write-Warning ".env not found at $envFile"
    return
}
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    if ($line -match '^\s*([^#=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
        Set-Item -Path "env:$name" -Value $value
    }
}
$root = Split-Path $PSScriptRoot -Parent
$env:PYTHONPATH = $root
Write-Host "Loaded .env from $envFile"
Write-Host "  FILEKG_GRAPH_BACKEND=$env:FILEKG_GRAPH_BACKEND"
Write-Host "  PYTHONPATH=$env:PYTHONPATH"
