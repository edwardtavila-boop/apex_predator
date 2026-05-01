# ============================================================================
# supercharge_vps.ps1 -- Second-round VPS tuning (beyond optimize_vps.ps1)
#
# Adds:
#   #11 Process priority boost for hot-path services (AboveNormal)
#   #12 Windows power plan -> High Performance
#   #13 Python bytecode precompile (.venv)
#   #15 Windows Time sync -> time.cloudflare.com (stratum-1)
#   #21 TCP window scaling + autotuning
#   #22 Apex PowerShell $PROFILE with helper aliases
#
# Idempotent. Report OK/SKIP per step.
# ============================================================================
[CmdletBinding()]
param(
    [string]$InstallDir = "C:\EvolutionaryTradingAlgo\eta_engine"
)

function Log  { param($m) Write-Host "[supercharge] $m" -ForegroundColor Cyan }
function OK   { param($m) Write-Host "[ OK ] $m" -ForegroundColor Green }
function Skip { param($m) Write-Host "[SKIP] $m" -ForegroundColor Yellow }
function Warn { param($m) Write-Host "[WARN] $m" -ForegroundColor DarkYellow }

$workspaceRoot = Split-Path -Parent $InstallDir
$stateDir = Join-Path $workspaceRoot "var\eta_engine\state"
$logDir = Join-Path $workspaceRoot "logs\eta_engine"

# ----------------------------------------------------------------------------
# #12 -- Power plan -> High Performance
# ----------------------------------------------------------------------------
Log "Step 1/6 -- Windows power plan -> High Performance"
try {
    # GUID for High Performance is 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
    & powercfg /setactive "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c" 2>&1 | Out-Null
    $current = (powercfg /getactivescheme) -replace '.*\((.+)\).*','$1'
    OK "active plan: $current"
} catch {
    Warn "powercfg: $($_.Exception.Message)"
}

# ----------------------------------------------------------------------------
# #11 -- Hot-path process priority wrapper
# ----------------------------------------------------------------------------
Log "Step 2/6 -- hot-path priority helper"
# We can't change priority of a scheduled task's payload via Task Scheduler
# directly, so we register a small priority-setter task that runs every minute
# and bumps Apex-Jarvis-Live / Apex-Avengers-Fleet / Apex-Dashboard processes
# to AboveNormal if they've dropped to Normal.
$priorityScript = Join-Path $InstallDir "deploy\scripts\priority_boost.ps1"
$priorityContent = @'
# Run every minute -- bump hot-path python processes to AboveNormal.
$targets = @{
    "jarvis_live"      = "AboveNormal"
    "avengers_daemon"  = "AboveNormal"
    "uvicorn"          = "AboveNormal"
    "cloudflared"      = "Normal"
}
Get-Process -Name python, cloudflared -ErrorAction SilentlyContinue | ForEach-Object {
    $p = $_
    $cmdline = (Get-WmiObject Win32_Process -Filter "ProcessId = $($p.Id)").CommandLine
    if (-not $cmdline) { return }
    foreach ($key in $targets.Keys) {
        if ($cmdline -match $key) {
            $want = $targets[$key]
            $map = @{ "AboveNormal" = [System.Diagnostics.ProcessPriorityClass]::AboveNormal;
                      "Normal"      = [System.Diagnostics.ProcessPriorityClass]::Normal }
            if ($p.PriorityClass -ne $map[$want]) {
                try { $p.PriorityClass = $map[$want] } catch {}
            }
            break
        }
    }
}
'@
Set-Content -Path $priorityScript -Value $priorityContent -Encoding UTF8 -Force

$taskName = "Apex-Priority-Boost"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$priorityScript`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration (New-TimeSpan -Days 9999)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $taskName
OK "Apex-Priority-Boost registered + started (runs every minute)"

# ----------------------------------------------------------------------------
# #13 -- Python bytecode precompile
# ----------------------------------------------------------------------------
Log "Step 3/6 -- precompiling .venv bytecode"
$venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    try {
        & $venvPython -m compileall -q -f `
            (Join-Path $InstallDir ".venv\Lib\site-packages") `
            (Join-Path $InstallDir "brain") `
            (Join-Path $InstallDir "deploy") `
            2>&1 | Out-Null
        OK "bytecode compiled (cold-start latency down)"
    } catch {
        Warn "compileall: $($_.Exception.Message)"
    }
} else {
    Skip "no .venv found"
}

# ----------------------------------------------------------------------------
# #15 -- Windows Time sync to Cloudflare
# ----------------------------------------------------------------------------
Log "Step 4/6 -- NTP -> time.cloudflare.com"
try {
    & w32tm /config /manualpeerlist:"time.cloudflare.com,0x8 time.nist.gov,0x8" /syncfromflags:manual /reliable:yes /update 2>&1 | Out-Null
    & w32tm /resync 2>&1 | Out-Null
    OK "time sync: time.cloudflare.com + time.nist.gov fallback"
} catch {
    Warn "w32tm needs Administrator: $($_.Exception.Message)"
}

# ----------------------------------------------------------------------------
# #21 -- TCP tuning
# ----------------------------------------------------------------------------
Log "Step 5/6 -- TCP window scaling + autotuning"
try {
    & netsh int tcp set global autotuninglevel=normal 2>&1 | Out-Null
    & netsh int tcp set global rss=enabled 2>&1 | Out-Null
    & netsh int tcp set global ecncapability=enabled 2>&1 | Out-Null
    OK "TCP autotuning=normal, rss=enabled, ECN=enabled"
} catch {
    Warn "netsh needs Administrator: $($_.Exception.Message)"
}

# ----------------------------------------------------------------------------
# #22 -- Apex PowerShell $PROFILE aliases
# ----------------------------------------------------------------------------
Log "Step 6/6 -- PowerShell profile aliases (apex-*)"
$profilePath = $PROFILE.CurrentUserAllHosts
if (-not (Test-Path (Split-Path $profilePath))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $profilePath) | Out-Null
}
$marker = "# --- BEGIN apex aliases ---"
$existing = if (Test-Path $profilePath) { Get-Content $profilePath -Raw } else { "" }
if ($existing -match [regex]::Escape($marker)) {
    Skip "profile already contains apex aliases"
} else {
    $apexBlock = @"

$marker
`$global:ETA_ROOT    = "$InstallDir"
`$global:ETA_PY      = "$InstallDir\.venv\Scripts\python.exe"
`$global:ETA_STATE   = "$stateDir"
`$global:ETA_LOGS    = "$logDir"

function apex-status    { & `$global:ETA_PY -m deploy.scripts.smoke_check --skip-systemd }
function apex-heartbeat { Get-Content "`$global:ETA_STATE\avengers_heartbeat.json" | ConvertFrom-Json | ConvertTo-Json }
function eta-dashboard { Get-Content "`$global:ETA_STATE\dashboard_payload.json" | ConvertFrom-Json | ConvertTo-Json -Depth 6 }
function apex-tasks     { Get-ScheduledTask -TaskName "Apex-*" | Select-Object TaskName, State | Format-Table -AutoSize }
function apex-logs      { param(`$n = 50) Get-Content "`$global:ETA_LOGS\avengers-fleet.log" -Tail `$n -Wait }
function apex-restart   { Stop-ScheduledTask "Apex-Jarvis-Live","Apex-Avengers-Fleet","Apex-Dashboard" -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2; Start-ScheduledTask "Apex-Jarvis-Live"; Start-ScheduledTask "Apex-Avengers-Fleet"; Start-ScheduledTask "Apex-Dashboard" }
function apex-test      { & `$global:ETA_PY -m deploy.scripts.live_claude_smoke }
function apex-task      { param([string]`$Task) & `$global:ETA_PY -m deploy.scripts.run_task `$Task --state-dir "`$global:ETA_STATE" --log-dir "`$global:ETA_LOGS" }
function apex-health    { Invoke-RestMethod http://127.0.0.1:8000/health }
# --- END apex aliases ---
"@
    Add-Content -Path $profilePath -Value $apexBlock -Encoding UTF8
    OK "profile updated: $profilePath"
    OK "aliases: apex-status, apex-heartbeat, eta-dashboard, apex-tasks, apex-logs, apex-restart, apex-test, apex-task, apex-health"
}

Write-Host ""
Log "supercharge pass complete."
Write-Host "  Active in next PowerShell session (or re-source profile)." -ForegroundColor Cyan
