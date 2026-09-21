# Tests laufen ohne laufendes Ollama - alle Provider-Aufrufe sind gemockt.
$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "..\backend" | Resolve-Path
Set-Location $backend

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
& ".venv\Scripts\python.exe" -m pytest -q
