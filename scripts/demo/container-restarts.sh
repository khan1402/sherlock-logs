#!/usr/bin/env bash
# container-restarts.sh - review test: "a container restarts more than 3 times in 15 minutes".
#
#   bash scripts/demo/container-restarts.sh <vm>        start the crash loop
#   bash scripts/demo/container-restarts.sh <vm> stop   remove the container
#
# The container exits with an error after 10 s and Docker restarts it
# (--restart=always), again and again. Each restart begins a new CPU counter
# at 0 in cAdvisor, and the alert counts those resets.
# Expected: "Container restarting" (test_container) within about a minute.

# The scripts below in single quotes run ON the VM, so their $variables must
# NOT expand here on the laptop - single quotes are intended (SC2016).
# shellcheck disable=SC2016
# shellcheck source=/dev/null  # _common.sh sits next to this script
source "$(dirname "$0")/_common.sh"

VM="${1:-}"; ARG="${2:-start}"
require_vm "$VM"

if [[ "$ARG" == "stop" ]]; then
  on_vm "$VM" 'sudo docker rm -f test_container >/dev/null && echo "test_container removed"'
  exit 0
fi

on_vm "$VM" '
  command -v docker >/dev/null || { echo "$(hostname) has no Docker - pick a Docker VM"; exit 1; }
  sudo docker rm -f test_container >/dev/null 2>&1 || true
  sudo docker run -d --restart=always --name test_container ubuntu:22.04 bash -c "sleep 10; exit 1" >/dev/null
  echo "test_container started on $(hostname): it crashes every 10 s and Docker restarts it"
'
echo "Expected: 'Container restarting' on $VM within ~1 min. Clean up: bash scripts/demo/container-restarts.sh $VM stop"
where_to_look
