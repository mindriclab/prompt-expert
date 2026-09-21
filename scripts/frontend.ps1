# Frontend im Entwicklungsmodus: Vite auf 5173, /api geht per Proxy an das Backend.
# Das Backend muss parallel laufen (start.bat oder scripts\dev.ps1).
$ErrorActionPreference = "Stop"
$frontend = Join-Path $PSScriptRoot "..\frontend" | Resolve-Path
Set-Location $frontend

if (-not (Test-Path "node_modules")) {
    Write-Host "[Setup] Abhaengigkeiten werden installiert..."
    npm install --no-fund --no-audit
}
npm run dev
