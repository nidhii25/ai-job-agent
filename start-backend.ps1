param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$python = Join-Path $backend "venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Backend virtual environment not found. Follow the setup steps in README.md first."
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Warning "backend\.env is missing. Copy backend\.env.example to backend\.env and configure it."
}

Push-Location $backend
try {
    & $python -m uvicorn main:app --host 127.0.0.1 --port $Port
}
finally {
    Pop-Location
}
