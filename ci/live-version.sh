#!/usr/bin/env bash
# live-version.sh - print the app version users see RIGHT NOW (through the
# load balancer). Prints nothing if the site is down.
#
#   bash ci/live-version.sh http://192.168.56.10/
#
# The pipeline records this BEFORE deploying, so it knows what to roll back to.
URL="${1:-http://192.168.56.10/}"

curl -sf -m 5 "${URL%/}/health" \
  | python3 -c 'import json, sys; print(json.load(sys.stdin).get("version", ""))' 2>/dev/null \
  || true
