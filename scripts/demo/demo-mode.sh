#!/usr/bin/env bash
# demo-mode.sh - shorter alert windows for the 45-minute review.
#
#   bash scripts/demo/demo-mode.sh on    5-minute "sustained" alerts fire after 1 minute
#   bash scripts/demo/demo-mode.sh off   back to the real 5 minutes (do this after the review)
#
# Re-applies ONLY the monitoring stack (site.yml --tags monitoring) with
# monitoring_alert_demo_mode=true|false. Thresholds (80%, 90%...) never change.
# Runs Ansible on the control node; sync your latest changes there first
# (scripts/sync-to-cicd.sh) if you edited anything on the laptop.

# The scripts below in single quotes run ON the VM, so their $variables must
# NOT expand here on the laptop - single quotes are intended (SC2016).
# shellcheck disable=SC2016
# shellcheck source=/dev/null  # _common.sh sits next to this script
source "$(dirname "$0")/_common.sh"

case "${1:-}" in
  on)  MODE=true ;;
  off) MODE=false ;;
  *)   echo "usage: bash scripts/demo/demo-mode.sh on|off" >&2; exit 1 ;;
esac
require_vm "$CONTROL_VM"

echo "Applying demo mode = $MODE on the monitoring stack (about 1 minute)..."
on_vm "$CONTROL_VM" '
  cd ~/sherlock-logs/ansible
  ansible-playbook site.yml --tags monitoring -e "monitoring_alert_demo_mode=$1"
' "$MODE"
echo "Demo mode is now: ${1}"
