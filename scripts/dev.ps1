# Entwicklungsmodus: Autoreload und Dev-Abhaengigkeiten.
$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "..\backend" | Resolve-Path
Set-Location $backend

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[Setup] Virtuelle Umgebung wird angelegt..."
    py -3.12 -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8756 --reload
