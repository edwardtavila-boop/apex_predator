@echo off
REM =============================================================================
REM apex.cmd -- Evolutionary Trading Algo launcher for the JARVIS + Avengers stack.
REM The existing jarvis.cmd launches hermes-agent. This launcher points at our
REM deterministic risk-gate + Avengers fleet inside the canonical ETA workspace.
REM =============================================================================
setlocal
for %%I in ("%~dp0..\..") do set "ETA_ROOT=%%~fI"
for %%I in ("%ETA_ROOT%\..") do set "WORKSPACE_ROOT=%%~fI"
set "ETA_PY=%ETA_ROOT%\.venv\Scripts\python.exe"
set "ETA_STATE=%WORKSPACE_ROOT%\var\eta_engine\state"
set "ETA_LOG=%WORKSPACE_ROOT%\logs\eta_engine"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if "%~1"=="status" (
    "%ETA_PY%" -m deploy.scripts.smoke_check --skip-systemd
    exit /b %ERRORLEVEL%
)
if "%~1"=="heartbeat" (
    type "%ETA_STATE%\avengers_heartbeat.json"
    exit /b 0
)
if "%~1"=="task" (
    "%ETA_PY%" -m deploy.scripts.run_task %~2 --state-dir "%ETA_STATE%" --log-dir "%ETA_LOG%"
    exit /b %ERRORLEVEL%
)
if "%~1"=="tasks" (
    powershell -NoProfile -Command "Get-ScheduledTask -TaskName Apex-* | Select-Object TaskName, State | Format-Table -AutoSize"
    exit /b 0
)
if "%~1"=="logs" (
    powershell -NoProfile -Command "Get-Content '%ETA_LOG%\avengers-fleet.log' -Tail 50 -Wait"
    exit /b 0
)
if "%~1"=="dashboard" (
    powershell -NoProfile -Command "Get-Content '%ETA_STATE%\dashboard_payload.json' | ConvertFrom-Json | ConvertTo-Json -Depth 5"
    exit /b 0
)
if "%~1"=="" (
    echo Evolutionary Trading Algo launcher
    echo.
    echo Usage: apex ^<command^>
    echo.
    echo   apex status      -- run smoke check
    echo   apex heartbeat   -- show latest avengers heartbeat
    echo   apex dashboard   -- show latest dashboard payload
    echo   apex tasks       -- list registered Task Scheduler entries
    echo   apex task NAME   -- manually fire a BackgroundTask (KAIZEN_RETRO, etc.)
    echo   apex logs        -- tail avengers-fleet log
    echo.
    exit /b 0
)
echo unknown command: %~1
exit /b 2
