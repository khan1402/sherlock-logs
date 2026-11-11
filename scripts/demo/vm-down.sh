#!/usr/bin/env bash
# vm-down.sh - review test: "a VM becomes unreachable".
#
#   bash scripts/demo/vm-down.sh <vm> [seconds]   (default 150 s)
#
# Switches off the VM's private network interface - the one with its project
# IP - and switches it on again AUTOMATICALLY after the given time. (Plain
# 'ifconfig eth0 down' would also cut our own SSH session, and nobody could
# switch it back on.) The restore runs as a systemd service on the VM, so it
# happens even though this SSH connection is cut.
# Expected: "VM unreachable" after about 1 minute, "Resolved" after the restore.

# The scripts below in single quotes run ON the VM, so their $variables must
# NOT expand here on the laptop - single quotes are intended (SC2016).
# shellcheck disable=SC2016
# shellcheck source=/dev/null  # _common.sh sits next to this script
source "$(dirname "$0")/_common.sh"

VM="${1:-}"; SECONDS_DOWN="${2:-150}"
require_vm "$VM"
if [[ "$VM" == "$MON_VM" ]]; then
  echo "Not the monitoring VM: Prometheus runs there - it would see EVERY VM as down." >&2
  exit 1
fi

on_vm "$VM" '
  ip_addr="$1"; seconds="$2"
  iface=$(ip -o -4 addr show | awk -v ip="$ip_addr" "index(\$4, ip\"/\") == 1 {print \$2}")
  [[ -n "$iface" ]] || { echo "No interface with $ip_addr found"; exit 1; }
  sudo -v   # ask for the sudo password now, while the network is still up
  # systemd-run starts the job as a system service, outside this SSH session.
  # (A background job with nohup was killed when the SSH session closed.)
  sudo systemd-run --quiet --collect --unit="demo-vm-down-$$" \
    bash -c "sleep 2; ip link set $iface down; sleep $seconds; ip link set $iface up"
  echo "$(hostname): $iface ($ip_addr) goes DOWN in 2 s and comes back by itself after $seconds s"
' "$(ip_of "$VM")" "$SECONDS_DOWN"
echo "Expected: 'VM unreachable' for $VM after ~1 min, then 'Resolved' about ${SECONDS_DOWN} s from now."
where_to_look
