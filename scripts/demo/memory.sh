#!/usr/bin/env bash
# memory.sh - review test: "memory usage above 90% for more than 5 minutes".
#
#   bash scripts/demo/memory.sh <vm> [seconds]   start (default 360 s)
#   bash scripts/demo/memory.sh <vm> stop        stop early
#
# stress-ng allocates (and keeps) all available memory except 5% of the total,
# so usage settles around 95%. The size is calculated on the VM itself, so it
# works on any VM size without risking the kernel's out-of-memory killer.
# Expected: "High memory usage" after 5 minutes (1 minute in demo mode).

# The scripts below in single quotes run ON the VM, so their $variables must
# NOT expand here on the laptop - single quotes are intended (SC2016).
# shellcheck disable=SC2016
# shellcheck source=/dev/null  # _common.sh sits next to this script
source "$(dirname "$0")/_common.sh"

VM="${1:-}"; ARG="${2:-360}"
require_vm "$VM"

if [[ "$ARG" == "stop" ]]; then
  on_vm "$VM" 'pkill -f "stress-ng --vm" && echo "Memory load stopped" || echo "No memory load was running"'
  exit 0
fi

ensure_stress_ng "$VM"
on_vm "$VM" '
  avail_kb=$(awk "/MemAvailable/ {print \$2}" /proc/meminfo)
  total_kb=$(awk "/MemTotal/ {print \$2}" /proc/meminfo)
  bytes=$(( (avail_kb - total_kb * 5 / 100) * 1024 ))
  # systemd-run starts the load as a service, outside this SSH session.
  # (A background job with nohup stopped as soon as the SSH session closed.)
  # --temp-path /tmp: a service starts in "/", where stress-ng may not write.
  sudo -v
  sudo systemd-run --quiet --collect --uid="$(id -un)" --unit="demo-memory-$$" \
    stress-ng --vm 1 --vm-bytes "$bytes" --vm-keep --timeout "$1s" --temp-path /tmp
  echo "Memory load started on $(hostname): $(( bytes / 1024 / 1024 )) MB for $1 s (target ~95% used)"
' "$ARG"
echo "Expected: 'High memory usage' on $VM after 5 min (1 min in demo mode)."
where_to_look
