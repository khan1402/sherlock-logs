#!/usr/bin/env bash
# disk.sh - review test: "available disk space falls below 20%".
#
#   bash scripts/demo/disk.sh <vm>        fill the disk until 15% is free
#   bash scripts/demo/disk.sh <vm> stop   delete the file again
#
# fallocate reserves the space instantly (no data is written). The size is
# calculated on the VM, so it works on any disk size.
# Expected: "Low disk space" after about 1 minute.
#
# Not on the monitoring VM: Elasticsearch itself reacts to a full disk (it
# stops placing replicas at 85% used), which would mix two demos into one.

# The scripts below in single quotes run ON the VM, so their $variables must
# NOT expand here on the laptop - single quotes are intended (SC2016).
# shellcheck disable=SC2016
# shellcheck source=/dev/null  # _common.sh sits next to this script
source "$(dirname "$0")/_common.sh"

VM="${1:-}"; ARG="${2:-start}"
require_vm "$VM"
if [[ "$VM" == "$MON_VM" ]]; then
  echo "Use another VM: Elasticsearch on $MON_VM reacts to a full disk by itself." >&2
  exit 1
fi

if [[ "$ARG" == "stop" ]]; then
  on_vm "$VM" 'rm -f ~/large_file.img && echo "Removed ~/large_file.img"; df -h / | tail -1'
  exit 0
fi

on_vm "$VM" '
  read -r avail size < <(df -B1 --output=avail,size / | tail -1)
  fill=$(( avail - size * 15 / 100 ))
  if (( fill <= 0 )); then echo "Already less than 15% free - nothing to do"; exit 0; fi
  fallocate -l "$fill" ~/large_file.img
  echo "Created ~/large_file.img ($(( fill / 1024 / 1024 )) MB):"
  df -h / | tail -1
'
echo "Expected: 'Low disk space' on $VM after ~1 min. Clean up: bash scripts/demo/disk.sh $VM stop"
where_to_look
