# Clone the 3 satellite repos onto the VPS so the operator-tooling
# tasks have something to run.
#
# Each repo is cloned to C:\<reponame>\ (or $InstallRoot\<reponame>\).
# If a repo already exists, this just runs `git pull` to refresh.
# Idempotent — safe to run repeatedly.
#
# Used by: vps_supercharge_bootstrap.ps1
[CmdletBinding()]
param(
    [string]$InstallRoot = "C:\",
    [string]$GitHubOwner = "edwardtavila-boop",
    [string]$Branch = "master",
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"

# --- repos to ensure on the VPS ---------------------------------------
# Each entry: GitHub repo name (https://github.com/<owner>/<name>) and
# the local directory under $InstallRoot. If the GitHub repo was renamed,
# we still use the new name -- GitHub auto-redirects from old URL.
$repos = @(
    @{ Name = "mnq_backtest";    LocalDir = "mnq_backtest";    Branch = "master" }
    @{ Name = "mnq_eta_bot";     LocalDir = "mnq_eta_bot";     Branch = "master" }
    @{ Name = "jarvis_identity"; LocalDir = "jarvis_identity"; Branch = "main" }
)

# --- pre-flight -------------------------------------------------------
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Write-Host "[satellite-repos] FATAL: git is not on PATH. Install it first." -ForegroundColor Red
    exit 1
}
$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    Write-Host "[satellite-repos] WARN: gh CLI not found; falling back to https clone" -ForegroundColor Yellow
}

Write-Host "[satellite-repos] InstallRoot=$InstallRoot  Owner=$GitHubOwner  DryRun=$DryRun"
Write-Host ""

# --- clone or pull each ----------------------------------------------
foreach ($r in $repos) {
    $localPath = Join-Path $InstallRoot $r.LocalDir
    $url = "https://github.com/$GitHubOwner/$($r.Name).git"
    Write-Host "=== $($r.Name) -> $localPath ===" -ForegroundColor Cyan

    if (Test-Path (Join-Path $localPath ".git")) {
        Write-Host "  exists; running git pull"
        if (-not $DryRun) {
            Push-Location $localPath
            try {
                $currentBranch = (& git branch --show-current 2>$null).Trim()
                if ($currentBranch -ne $r.Branch) {
                    Write-Host "  switching from $currentBranch -> $($r.Branch)"
                    & git fetch origin $($r.Branch) 2>&1 | Out-Null
                    & git checkout $($r.Branch) 2>&1 | Out-Null
                }
                $pullOut = & git pull origin $($r.Branch) 2>&1
                Write-Host "  pull: $($pullOut | Select-Object -Last 1)"
            } finally {
                Pop-Location
            }
        }
    } else {
        Write-Host "  cloning $url"
        if (-not $DryRun) {
            $cloneOut = & git clone --branch $($r.Branch) $url $localPath 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  CLONE FAILED: $cloneOut" -ForegroundColor Red
                Write-Host "  -> verify the repo exists and your gh auth has read access" -ForegroundColor Yellow
                continue
            }
            Write-Host "  cloned $($r.Name) -> $localPath"
        } else {
            Write-Host "  (DryRun) would clone here"
        }
    }
    Write-Host ""
}

# --- summary ----------------------------------------------------------
Write-Host "=== summary ==="
foreach ($r in $repos) {
    $localPath = Join-Path $InstallRoot $r.LocalDir
    if (Test-Path (Join-Path $localPath ".git")) {
        Push-Location $localPath
        try {
            $sha = (& git rev-parse --short HEAD 2>$null).Trim()
            $msg = (& git log -1 --format="%s" 2>$null).Trim()
            Write-Host ("  OK   {0,-20} {1}  {2}" -f $r.Name, $sha, $msg)
        } finally {
            Pop-Location
        }
    } else {
        Write-Host ("  MISS {0}" -f $r.Name) -ForegroundColor Yellow
    }
}
