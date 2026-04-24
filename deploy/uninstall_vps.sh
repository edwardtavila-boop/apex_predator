#!/usr/bin/env bash
# ============================================================================
# EVOLUTIONARY TRADING ALGO // uninstall_vps.sh
# ----------------------------------------------------------------------------
# Safe rollback. Removes systemd units + cron entries. Does NOT delete the
# source code, .env, state, or log dirs (operator decides).
#
# Usage (as operator user):
#   ./deploy/uninstall_vps.sh               # interactive
#   ./deploy/uninstall_vps.sh --yes         # non-interactive
#   ./deploy/uninstall_vps.sh --purge       # also remove state + logs
# ============================================================================
set -euo pipefail

YES=0
PURGE=0
for arg in "$@"; do
  case "$arg" in
    --yes)   YES=1 ;;
    --purge) PURGE=1 ;;
    -h|--help) grep '^#' "$0" | head -20; exit 0 ;;
    *) echo "unknown flag $arg"; exit 2 ;;
  esac
done

if [[ "$YES" == "0" ]]; then
  read -r -p "This will stop systemd services + remove Avengers cron entries. Continue? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "aborted"; exit 1; }
fi

log() { printf '\033[36m[apex-uninstall]\033[0m %s\n' "$*"; }

# 1. Stop + disable systemd units
log "stopping systemd --user units"
for unit in eta-dashboard avengers-fleet jarvis-live; do
  systemctl --user stop    "$unit" 2>/dev/null || true
  systemctl --user disable "$unit" 2>/dev/null || true
done

# 2. Remove unit files
log "removing systemd unit files"
UNIT_DIR="$HOME/.config/systemd/user"
for unit in jarvis-live.service avengers-fleet.service eta-dashboard.service; do
  rm -f "$UNIT_DIR/$unit"
done
systemctl --user daemon-reload 2>/dev/null || true

# 3. Strip crontab entries tagged eta-engine:avengers
log "stripping crontab entries"
EXISTING="$(crontab -l 2>/dev/null || true)"
if [[ -n "$EXISTING" ]]; then
  printf '%s\n' "$EXISTING" | grep -v 'eta-engine:avengers' | crontab -
fi

# 4. Purge state + logs if requested
if [[ "$PURGE" == "1" ]]; then
  log "PURGE: removing state + logs"
  rm -rf "$HOME/.local/state/eta_engine"
  rm -rf "$HOME/.local/log/eta_engine"
fi

log "uninstall complete"
log "source code + .env preserved -- delete manually if desired"
