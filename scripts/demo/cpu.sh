#!/usr/bin/env bash
# cpu.sh - review test: "CPU usage above 80% for more than 5 minutes".
#
#   bash scripts/demo/cpu.sh <vm> [seconds]   start (default 360 s = 6 minutes)
#   bash scripts/demo/cpu.sh <vm> stop        stop early
#
# Runs stress-ng on ALL cores of the VM, in the background.
# Expected: "High CPU usage" fires after 5 minutes (1 minute in demo mode),
# then "Resolved" about a minute after the load stops.

# The scripts below in single quotes run ON the VM, so their $variables must
# NOT expand here on the laptop - single quotes are intended (SC2016).
# shellcheck disable=SC2016
# shellcheck source=/dev/null  # _common.sh sits next to this script
source "$(dirname "$0")/_common.sh"

VM="${1:-}"; ARG="${2:-360}"
require_vm "$VM"

if [[ "$ARG" == "stop" ]]; then
  on_vm "$VM" 'pkill -f "stress-ng --cpu" && echo "CPU load stopped" || echo "No CPU load was running"'
  exit 0
fi

ensure_stress_ng "$VM"
on_vm "$VM" '
  nohup stress-ng --cpu 0 --timeout "$1s" >/dev/null 2>&1 &
  echo "CPU load started on $(hostname): all $(nproc) cores at 100% for $1 s"
' "$ARG"
echo "Expected: 'High CPU usage' on $VM after 5 min (1 min in demo mode)."
where_to_look
