# Baut das Frontend nach frontend\dist. Danach liefert das Backend es unter / aus.
$ErrorActionPreference = "Stop"
$frontend = Join-Path $PSScriptRoot "..\frontend" | Resolve-Path
Set-Location $frontend

if (-not (Test-Path "node_modules")) {
    npm install --no-fund --no-audit
}
npm run build
Write-Host ""
Write-Host "Fertig. Backend neu starten, dann http://127.0.0.1:8756 oeffnen."
