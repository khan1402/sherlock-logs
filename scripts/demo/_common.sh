#!/usr/bin/env bash
# _common.sh - shared helpers for the review demo scripts (sourced, not run).
#
# Every demo runs from your LAPTOP (Git Bash or WSL), in the repo folder, and
# returns within seconds: the load itself runs in the background on the VM.
# VM names and IPs come from ansible/inventory/hosts.yml (single source of truth).
#
# Overrides (environment variables):
#   SSH_KEY     private key for the devops user   (default: keys/ansible_key)
#   MON_VM      the monitoring VM                  (default: monitoring-server)
#   CONTROL_VM  the VM that runs Ansible           (default: cicd-server)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1

INVENTORY=ansible/inventory/hosts.yml
SSH_KEY="${SSH_KEY:-keys/ansible_key}"
MON_VM="${MON_VM:-monitoring-server}"
CONTROL_VM="${CONTROL_VM:-cicd-server}"
SSH_OPTS=(-i "$SSH_KEY" -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR)

# IP of a VM name, read from the inventory ("" if the name is unknown).
ip_of() {
  awk -v host="$1" '$1 == host":" { found = 1; next } found && /ansible_host:/ { print $2; exit }' "$INVENTORY"
}

# Every VM name in the inventory.
vm_names() {
  awk '/^ *[a-z0-9-]+: *$/ { name = $1; sub(":", "", name) } /ansible_host:/ { print name }' "$INVENTORY"
}

# Stop with a helpful message unless $1 is a VM from the inventory.
require_vm() {
  if [[ -z "${1:-}" || -z "$(ip_of "$1")" ]]; then
    echo "Unknown or missing VM name '${1:-}'. Choose one of:" >&2
    vm_names | sed 's/^/  /' >&2
    exit 1
  fi
}

# Run a script ON a VM, with a terminal (-t) so sudo can ask for the devops
# password. The script is copied over first: no quoting problems.
#   on_vm <vm> <script-text> [args...]
on_vm() {
  local vm="$1" script="$2"; shift 2
  local ip remote="/tmp/sherlock-demo-$$.sh"
  ip="$(ip_of "$vm")"
  # $remote is meant to expand HERE (on the laptop): it is the file name on the VM.
  # shellcheck disable=SC2029
  ssh "${SSH_OPTS[@]}" "devops@$ip" "cat > $remote" <<<"$script"
  ssh -t "${SSH_OPTS[@]}" "devops@$ip" bash "$remote" "$@"
  # shellcheck disable=SC2029
  ssh "${SSH_OPTS[@]}" "devops@$ip" "rm -f $remote" 2>/dev/null || true
}

# Install stress-ng on a VM if it is missing (asks for the devops sudo password once).
ensure_stress_ng() {
  # shellcheck disable=SC2016  # single quotes on purpose: runs ON the VM
  on_vm "$1" 'command -v stress-ng >/dev/null || { echo "Installing stress-ng..."; sudo apt-get install -y -qq stress-ng >/dev/null; }'
}

# Where to watch the result.
where_to_look() {
  local mon_ip
  mon_ip="$(ip_of "$MON_VM")"
  echo
  echo "Watch it here:"
  echo "  Grafana alerts:  http://$mon_ip:3000/alerting/list"
  echo "  Dashboards:      http://$mon_ip:3000/dashboards (folder 'Sherlock Logs')"
  echo "  Prometheus:      http://$mon_ip:9090/targets (is every target up?)"
  echo "  Slack:           the alert message, then 'Resolved' when it is over"
}
