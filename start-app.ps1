$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Starting backend and frontend in separate PowerShell windows..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $root "start-backend.ps1")
)
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $root "start-frontend.ps1")
)

Start-Sleep -Seconds 3
Start-Process "http://localhost:3000"
Write-Host "Backend:  http://127.0.0.1:8000/api/health"
Write-Host "Frontend: http://localhost:3000"
