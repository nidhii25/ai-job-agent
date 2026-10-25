$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontend = Join-Path $root "frontend"

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    throw "Frontend dependencies are not installed. Run 'npm install' in frontend first."
}

Push-Location $frontend
try {
    npm run dev
}
finally {
    Pop-Location
}
