#!/usr/bin/env bash
# Install (or refresh) the gate-lite expiry-sweep systemd user timer.
#
# The one-shot service runs a single sweep pass:
#   python3 -m gate_lite.ctl --state <state> sweep
# which seals every past-expiry slot with a time_expired termination receipt.
# Sweeping no longer walks a JSON file (SQLite registry, 2026-09-18), so a
# 15-minute cadence is cheap; the orchestrator still self-seals on exec/kill/
# snapshot/restore, this only covers idle slots.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE="${WM_GATELITE_STATE:-$HOME/gate-state}"
INTERVAL="15min"
PYTHON="$(command -v python3 || true)"
DRY_RUN=0
UNINSTALL=0

usage() {
  cat <<EOF
usage: $(basename "$0") [--state PATH] [--interval RATE] [--repo PATH] [--dry-run] [--uninstall]

  --state PATH      gate-lite state dir (default: \$WM_GATELITE_STATE or ~/gate-state)
  --interval RATE   systemd OnUnitActiveSec value (default: 15min)
  --repo PATH       gate-lite checkout (default: this script's parent)
  --dry-run         print the rendered units, install nothing
  --uninstall       disable and remove the timer and service
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --state) STATE="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$PYTHON" ]]; then
  echo "python3 not found on PATH" >&2
  exit 1
fi

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE="$UNIT_DIR/mandala-sweep.service"
TIMER="$UNIT_DIR/mandala-sweep.timer"

render_service() {
  cat <<EOF
[Unit]
Description=Mandala gate-lite expiry sweep
Documentation=file://$REPO/HANDOFF_2026-09-18.md

[Service]
Type=oneshot
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO
ExecStart="$PYTHON" -m gate_lite.ctl --state "$STATE" sweep
EOF
}

render_timer() {
  cat <<EOF
[Unit]
Description=Run the Mandala gate-lite expiry sweep periodically

[Timer]
OnBootSec=5min
OnUnitActiveSec=$INTERVAL
Persistent=true
Unit=mandala-sweep.service

[Install]
WantedBy=timers.target
EOF
}

if [[ "$DRY_RUN" == "1" ]]; then
  echo "== $SERVICE =="
  render_service
  echo
  echo "== $TIMER =="
  render_timer
  exit 0
fi

if [[ "$UNINSTALL" == "1" ]]; then
  systemctl --user disable --now mandala-sweep.timer 2>/dev/null || true
  rm -f "$SERVICE" "$TIMER"
  systemctl --user daemon-reload
  echo "removed mandala-sweep timer and service"
  exit 0
fi

mkdir -p "$UNIT_DIR"
render_service > "$SERVICE"
render_timer > "$TIMER"
systemctl --user daemon-reload
systemctl --user enable --now mandala-sweep.timer
systemctl --user list-timers mandala-sweep.timer --no-pager
