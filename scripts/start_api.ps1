. "$PSScriptRoot\load_env.ps1"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
