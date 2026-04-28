# Edge + Tunnel install runbook — last 5 minutes of 24/7 setup

**Status as of 2026-04-27, commit 7ecf989+**

The runtime backbone (FirmCore + FirmCommandCenter + FirmWatchdog +
14 scheduled tasks) is RUNNING 24/7. The Edge proxy + Cloudflare
Tunnel layers — which expose the dashboard to the internet — are
**90% staged**. Only one user-action step remains: getting a
Cloudflare tunnel token.

This doc captures what's done, what's left, and how to finish.

## Current state — files staged on this VPS

```
C:\EvolutionaryTradingAlgo\firm_command_center\services\
├── caddy.exe                     ✅ 50 MB  (2026-04-27 download)
├── cloudflared.exe               ✅ 63 MB  (2026-04-27 download)
├── FirmCommandCenter.Caddyfile   ✅ 2.3 KB (reverse-proxy 8081 -> 8420)
├── FirmCommandCenterEdge.xml     ✅ 677 B  (winsw config)
├── FirmCommandCenterEdge.exe     ✅ winsw wrapper (renamed)
├── FirmCommandCenterTunnel.xml   ✅ 709 B  (winsw config)
├── FirmCommandCenterTunnel.exe   ✅ winsw wrapper (renamed)
└── winsw.exe                     ✅ source winsw binary
```

## What's missing — the tunnel token (only manual step)

`cloudflared.exe` needs a tunnel token to authenticate with Cloudflare.
Generating one requires logging into a Cloudflare account; cannot be
automated from this side.

## Step-by-step finish

### 1. Get the Cloudflare tunnel token (~5 min, requires Cloudflare account)

1. Sign in to **Cloudflare Zero Trust dashboard**:
   https://one.dash.cloudflare.com/
2. Navigate to: **Networks → Tunnels → Create a tunnel**
3. Choose **Cloudflared** connector type
4. Name the tunnel: `eta-command-center` (or any preferred slug)
5. After creation, Cloudflare displays an **install command** containing
   the token. It looks like:
   ```
   cloudflared.exe service install eyJhIjoiYWFhYWFhYS....[long base64]
   ```
6. **Copy ONLY the base64 token** (everything after `service install`)
7. On the VPS, save it to:
   ```
   C:\EvolutionaryTradingAlgo\firm_command_center\secrets\cloudflare_tunnel_token.txt
   ```
   The file should contain the token on a single line, no quotes,
   no extra whitespace, no `service install` prefix.

### 2. Configure the tunnel route (in Cloudflare dashboard)

In the same tunnel-creation flow, when prompted for **Public Hostname**:

| Field | Value |
|---|---|
| Subdomain | `command-center` |
| Domain | `<your domain>` (e.g. `evolutionarytradingalgo.com`) |
| Path | (empty) |
| Service Type | `HTTP` |
| URL | `localhost:8081` |

This tells Cloudflare to route `command-center.<domain>` traffic
through the tunnel to Caddy on `127.0.0.1:8081`, which then reverse-
proxies to FirmCommandCenter on `127.0.0.1:8420`.

### 3. Install + start the services (one command)

Open an **Administrator PowerShell** on the VPS, then run:

```powershell
cd C:\EvolutionaryTradingAlgo\firm_command_center\services

# Install both services as Windows Services
.\FirmCommandCenterEdge.exe install
.\FirmCommandCenterTunnel.exe install

# Set both to Automatic start (required for 24/7)
Set-Service FirmCommandCenterEdge -StartupType Automatic
Set-Service FirmCommandCenterTunnel -StartupType Automatic

# Start both
Start-Service FirmCommandCenterEdge
Start-Service FirmCommandCenterTunnel

# Verify
Get-Service FirmCommandCenter*
```

### 4. Confirm with the runtime audit

```powershell
& C:\EvolutionaryTradingAlgo\eta_engine\scripts\runtime_readiness_check.ps1
```

Expected:
```
--- Services (Layer 1) ---
  FirmCore                       Running    Automatic
  FirmCommandCenter              Running    Automatic
  FirmWatchdog                   Running    Automatic
  FirmCommandCenterEdge          Running    Automatic   (NEW)
  FirmCommandCenterTunnel        Running    Automatic   (NEW)

Summary:
  Services:  5/5
  Tasks:     14/17
  Issues:    0
  Overall:   READY
```

### 5. Smoke-test the public dashboard (~30 seconds)

From any browser anywhere on the internet:
```
https://command-center.<your-domain>
```

You should see the FirmCommandCenter dashboard. If you get a
Cloudflare 1033 error ("tunnel not connected"), check the cloudflared
log:
```powershell
Get-Content C:\EvolutionaryTradingAlgo\firm_command_center\var\logs\cloudflared.out.log -Tail 50
```

If you get a 502 from Caddy, the upstream uvicorn isn't responding —
verify `Get-Service FirmCommandCenter` returns Running and that
`http://127.0.0.1:8420/health` returns 200 from the VPS.

## Optional: protect the dashboard with Cloudflare Access

In the Cloudflare Zero Trust dashboard:
1. **Access → Applications → Add an application**
2. Type: `Self-hosted`
3. Application domain: `command-center.<your-domain>`
4. Add an **Access Policy** with allowed users (your email + any
   teammate emails, or a group)

Once this is in place, every visit to the dashboard requires
Cloudflare Access auth (Google/GitHub/email-OTP). This is the
strongest security setup; without it the only protection is "the
domain isn't publicly indexed".

## What this enables

* Remote dashboard access from any device with internet (no VPN/RDP needed)
* Encrypted end-to-end (Cloudflare TLS to edge, tunnel inside)
* Optional Cloudflare Access for SSO/MFA
* Audit log via Caddy access log (rolling, 50 MB segments, 5 retention)
* Auto-restart on crash (winsw `onfailure restart 10s`)

## Rollback / uninstall

If you want to remove the public dashboard layer later:

```powershell
cd C:\EvolutionaryTradingAlgo\firm_command_center\services
Stop-Service FirmCommandCenterEdge, FirmCommandCenterTunnel
.\FirmCommandCenterEdge.exe uninstall
.\FirmCommandCenterTunnel.exe uninstall
```

The trading layer (FirmCore + FirmCommandCenter + FirmWatchdog +
14 scheduled tasks) is unaffected — it runs 24/7 regardless of
whether the dashboard is publicly accessible.
