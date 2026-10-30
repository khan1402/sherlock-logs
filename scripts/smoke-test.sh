#!/usr/bin/env bash
# smoke-test.sh - check the live app through the load balancer after a deploy.
#
#   bash scripts/smoke-test.sh <url> <expected-version> [requests]
#   bash scripts/smoke-test.sh http://192.168.56.10/ 3f2a1bc
#
# Passes only if EVERY request:
#   - returns HTTP 200
#   - shows "Frontend <version>"  (the new web server image is running)
#   - shows "Backend <version>"   (the new backend answers the web server)
# and the answers came from at least 2 different web servers (load balancing).
set -euo pipefail

URL="${1:?usage: smoke-test.sh <url> <expected-version> [requests]}"
VERSION="${2:?usage: smoke-test.sh <url> <expected-version> [requests]}"
REQUESTS="${3:-6}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { echo "FAIL: $*"; exit 1; }

echo "Smoke test: ${REQUESTS} requests to ${URL}, expecting version ${VERSION}"
servers=()
for i in $(seq 1 "$REQUESTS"); do
  code="$(curl -s -m 10 -o "$TMP/body" -D "$TMP/headers" -w '%{http_code}' "$URL" || true)"
  upstream="$(grep -i '^x-upstream:' "$TMP/headers" 2>/dev/null | awk '{print $2}' | tr -d '\r' || true)"

  [[ "$code" == "200" ]]                     || fail "request $i: HTTP ${code:-none} (via ${upstream:-?})"
  grep -q "Frontend ${VERSION}" "$TMP/body"  || fail "request $i: frontend is not version ${VERSION} (via ${upstream})"
  grep -q "Backend ${VERSION}" "$TMP/body"   || fail "request $i: backend is not version ${VERSION} (via ${upstream})"

  echo "  request $i OK  (served by ${upstream})"
  servers+=("$upstream")
done

unique="$(printf '%s\n' "${servers[@]}" | sort -u | wc -l)"
(( unique >= 2 )) || fail "all requests went to one web server - load balancing is not working"

echo "PASS: version ${VERSION} is live on ${unique} web servers"


