#!/usr/bin/env bash
# validate.sh - check the whole infrastructure against the review checklist.
#
#   bash scripts/validate.sh           # the 5 core VMs
#   bash scripts/validate.sh --bonus   # + backup server, Fail2Ban, backups
#
# Run on your LAPTOP, in Git Bash, from the repo folder. Read-only: it changes
# nothing. The VM list comes from ansible/inventory/hosts.yml (single source of truth).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

BONUS=false
[[ "${1:-}" == "--bonus" ]] && BONUS=true

KEY=keys/ansible_key
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR)
LB_IP=192.168.56.10
PASSED=0
FAILED=0

pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; PASSED=$((PASSED + 1)); }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=$((FAILED + 1)); }
title() { printf '\n\033[1m%s\033[0m\n' "$1"; }
expect() {   # expect "<description>" <command...>   -> PASS if the command succeeds
  local description="$1"; shift
  if "$@"; then pass "$description"; else fail "$description"; fi
}

# --- VM list from the inventory: "<hostname> <ip> <bonus>" per line ------------------
mapfile -t VMS < <(awk '
  /^ *[a-z0-9-]+: *$/ { name = $1; sub(":", "", name) }
  /ansible_host:/     { ip[name] = $2; order[++n] = name }
  /bonus: *true/      { bonus[name] = 1 }
  END { for (i = 1; i <= n; i++) print order[i], ip[order[i]], (bonus[order[i]] ? "bonus" : "core") }
' ansible/inventory/hosts.yml)

role_of() {
  case "$1" in
    load-balancer*) echo lb ;;  web-server*) echo web ;;  app-server*) echo app ;;
    cicd-server*)   echo cicd ;; *)          echo backup ;;
  esac
}

HOSTS=()
for line in "${VMS[@]}"; do
  read -r name ip kind <<<"$line"
  [[ "$kind" == "bonus" && "$BONUS" != "true" ]] && continue
  HOSTS+=("$name $ip")
done

title "Infrastructure: ${#HOSTS[@]} VMs in the inventory"
expect "at least 5 VMs defined" test "${#HOSTS[@]}" -ge 5

# --- 1. Checks ON each VM -------------------------------------------------------------
for entry in "${HOSTS[@]}"; do
  read -r name ip <<<"$entry"
  title "$name ($ip)"
  peers=()
  for other in "${HOSTS[@]}"; do
    read -r other_name _ <<<"$other"
    [[ "$other_name" != "$name" ]] && peers+=("$other_name")
  done

  errors="$(mktemp)"
  output="$("${SSH[@]}" "devops@$ip" "bash -s -- $(role_of "$name") $name $ip $BONUS ${peers[*]}" \
             < scripts/remote-checks.sh 2>"$errors")"
  if [[ -z "$output" ]]; then
    fail "devops can log in with the SSH key ($(head -n 1 "$errors" | tr -d '\r'))"
    rm -f "$errors"; continue
  fi
  rm -f "$errors"
  pass "devops can log in with the SSH key"
  while read -r result text; do
    [[ "$result" == "PASS" ]] && pass "$text"
    [[ "$result" == "FAIL" ]] && fail "$text"
  done <<<"$output"

  # Login policy, tested from OUTSIDE: these attempts must be refused.
  if "${SSH[@]}" "root@$ip" true 2>/dev/null; then fail "root login is refused"; else pass "root login is refused"; fi
  answer="$(ssh -o BatchMode=yes -o PubkeyAuthentication=no -o PreferredAuthentications=password \
                -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new "devops@$ip" true 2>&1)"
  if grep -q 'Permission denied (publickey)' <<<"$answer"; then
    pass "password login is refused (key only)"
  else
    fail "password login is refused (key only)"
  fi
done

# --- 2. What the outside world can reach --------------------------------------------
title "Network access from this laptop"
code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://$LB_IP/")"
expect "load balancer answers on http://$LB_IP (HTTP $code)" test "$code" = 200
code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://localhost:8080/")"
expect "app reachable on http://localhost:8080 (HTTP $code)" test "$code" = 200

version="$(curl -s -m 10 "http://$LB_IP/health" | sed -n 's/.*"version": *"\([^"]*\)".*/\1/p')"
expect "running version is visible on /health: ${version:-none}" test -n "$version"

upstreams="$(for _ in 1 2 3 4 5 6; do
  curl -s -m 10 -D - -o /dev/null "http://$LB_IP/" | tr -d '\r' | awk 'tolower($1) == "x-upstream:" { print $2 }'
done | sort -u | xargs)"
count="$(wc -w <<<"$upstreams")"
expect "load balancer spreads requests over: ${upstreams:-none}" test "$count" -ge 2

for target in 192.168.56.11:80 192.168.56.12:80 192.168.56.13:3000; do
  if curl -s -m 4 -o /dev/null "http://$target/"; then
    fail "$target is NOT reachable directly (only the load balancer is)"
  else
    pass "$target is NOT reachable directly (only the load balancer is)"
  fi
done

code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://192.168.56.14:8080/login")"
expect "Jenkins UI answers, admin laptop only (HTTP $code)" test "$code" = 200

# --- Summary --------------------------------------------------------------------------
echo
if (( FAILED == 0 )); then
  printf '\033[32mALL %d CHECKS PASSED\033[0m\n' "$PASSED"
else
  printf '\033[31m%d FAILED\033[0m, %d passed\n' "$FAILED" "$PASSED"
fi
exit $(( FAILED > 0 ))
