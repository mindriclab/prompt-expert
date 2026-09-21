@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo [Setup] Virtuelle Umgebung wird angelegt...
    py -3.12 -m venv .venv
    if errorlevel 1 python -m venv .venv
    if errorlevel 1 (
        echo [Fehler] Python 3.12 wurde nicht gefunden.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [Fehler] Installation der Abhaengigkeiten fehlgeschlagen.
        pause
        exit /b 1
    )
)

rem Sprachunabhaengige Portpruefung - netstat meldet den Zustand lokalisiert.
set "BUSYPID="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8756 -State Listen -ErrorAction SilentlyContinue; if ($c) { @($c)[0].OwningProcess }"`) do set "BUSYPID=%%P"
if defined BUSYPID (
    echo.
    echo   [Hinweis] Port 8756 ist bereits durch Prozess !BUSYPID! belegt.
    echo   Es laeuft vermutlich schon eine Instanz: http://127.0.0.1:8756
    echo.
    echo   Falls nicht, den alten Prozess beenden:
    echo     taskkill /PID !BUSYPID! /F
    echo.
    pause
    exit /b 1
)

echo.
echo   Prompt Expert
echo.
echo   App:       http://127.0.0.1:8756
echo   API-Doku:  http://127.0.0.1:8756/docs
echo.
echo   Das Browserfenster oeffnet sich gleich von selbst.
echo   Beenden mit Strg+C
echo.

set "PE_OPEN_BROWSER=1"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8756
endlocal
