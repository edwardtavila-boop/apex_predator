@echo off
REM =============================================================================
REM apex.cmd -- Evolutionary Trading Algo launcher for the JARVIS + Avengers stack.
REM The existing jarvis.cmd launches hermes-agent. This launcher points at our
REM deterministic risk-gate + Avengers fleet at C:\eta_engine\.
REM =============================================================================
setlocal
set "APEX_ROOT=C:\eta_engine"
set "APEX_PY=%APEX_ROOT%\.venv\Scripts\python.exe"
set "APEX_STATE=%LOCALAPPDATA%\eta_engine\state"
set "APEX_LOG=%LOCALAPPDATA%\eta_engine\logs"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if "%~1"=="status" (
    "%APEX_PY%" -m deploy.scripts.smoke_check --skip-systemd
    exit /b %ERRORLEVEL%
)
if "%~1"=="heartbeat" (
    type "%APEX_STATE%\avengers_heartbeat.json"
    exit /b 0
)
if "%~1"=="task" (
    "%APEX_PY%" -m deploy.scripts.run_task %~2 --state-dir "%APEX_STATE%" --log-dir "%APEX_LOG%"
    exit /b %ERRORLEVEL%
)
if "%~1"=="tasks" (
    powershell -NoProfile -Command "Get-ScheduledTask -TaskName Apex-* | Select-Object TaskName, State | Format-Table -AutoSize"
    exit /b 0
)
if "%~1"=="logs" (
    powershell -NoProfile -Command "Get-Content '%APEX_LOG%\avengers-fleet.log' -Tail 50 -Wait"
    exit /b 0
)
if "%~1"=="dashboard" (
    powershell -NoProfile -Command "Get-Content '%APEX_STATE%\dashboard_payload.json' | ConvertFrom-Json | ConvertTo-Json -Depth 5"
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
