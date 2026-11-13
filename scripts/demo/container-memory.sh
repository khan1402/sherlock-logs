#!/usr/bin/env bash
# container-memory.sh - review test: "container memory above 80% of its limit".
#
#   bash scripts/demo/container-memory.sh <vm> [seconds]   start (default 360 s)
#   bash scripts/demo/container-memory.sh <vm> stop        remove the container
#
# A container with a 128 MB limit uses 110 MB (86%). Small on purpose: the
# web servers have only 768 MB, and a bigger test froze web-server-1.
# ubuntu has no stress-ng, so a small Alpine container installs it first.
# Expected: "Container near its memory limit" (memory_test) after about 1 minute.

# The scripts below in single quotes run ON the VM, so their $variables must
# NOT expand here on the laptop - single quotes are intended (SC2016).
# shellcheck disable=SC2016
# shellcheck source=/dev/null  # _common.sh sits next to this script
source "$(dirname "$0")/_common.sh"

VM="${1:-}"; ARG="${2:-360}"
require_vm "$VM"

if [[ "$ARG" == "stop" ]]; then
  on_vm "$VM" 'sudo docker rm -f memory_test >/dev/null && echo "memory_test removed"'
  exit 0
fi

on_vm "$VM" '
  command -v docker >/dev/null || { echo "$(hostname) has no Docker - pick a Docker VM"; exit 1; }
  sudo docker rm -f memory_test >/dev/null 2>&1 || true
  sudo docker run -d -m 128m --name memory_test alpine:3.20 \
    sh -c "apk add --no-cache -q stress-ng && stress-ng --vm 1 --vm-bytes 110M --vm-keep --timeout $1s" >/dev/null
  echo "memory_test started on $(hostname): 110 MB used of a 128 MB limit, for $1 s"
' "$ARG"
echo "Expected: 'Container near its memory limit' on $VM after ~1 min. Clean up: bash scripts/demo/container-memory.sh $VM stop"
where_to_look
