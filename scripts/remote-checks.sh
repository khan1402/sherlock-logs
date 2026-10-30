#!/usr/bin/env bash
# remote-checks.sh - runs ON one VM, called by validate.sh over SSH:
#   ssh devops@<ip> 'bash -s -- <role> <hostname> <ip> <bonus> <peer...>' < scripts/remote-checks.sh
#
# Read-only. Prints one line per check: "PASS <what>" or "FAIL <what>".
set -u

ROLE="$1"; NAME="$2"; IP="$3"; BONUS="$4"; shift 4
PEERS=("$@")

check() {   # check "<description>" <command...>
  local description="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "PASS $description"; else echo "FAIL $description"; fi
}

# --- Identity and network -------------------------------------------------------
check "hostname is $NAME"                     test "$(hostname)" = "$NAME"
check "static IP $IP is configured"           bash -c "ip -4 -o addr show | grep -q ' $IP/'"
for peer in "${PEERS[@]}"; do
  check "can ping $peer by name"              ping -c 1 -W 2 "$peer"
done

# --- Users and sudo -------------------------------------------------------------
check "devops is in the sudo group"           bash -c "id -nG devops | tr ' ' '\n' | grep -qx sudo"
check "sudo asks devops for a password"       bash -c "! sudo -n true"
check "default umask is 0027"                 test "$(umask)" = "0027"

# --- SSH policy (drop-in written by the hardening role) -------------------------
SSHD=/etc/ssh/sshd_config.d/00-hardening.conf
check "SSH: root login disabled"              grep -qix 'PermitRootLogin no' "$SSHD"
check "SSH: password login disabled"          grep -qix 'PasswordAuthentication no' "$SSHD"
check "SSH: only devops may log in"           grep -qix 'AllowUsers devops' "$SSHD"

# --- Firewall: active, and ONLY the ports this server needs ---------------------
case "$ROLE" in
  lb|web) want="22 80" ;;
  app)    want="22 3000" ;;
  cicd)   want="22 8080" ;;
  *)      want="22" ;;
esac
status="$(sudo -n ufw status 2>/dev/null)"
open="$(awk '/ALLOW/ { split($1, port, "/"); print port[1] }' <<<"$status" | sort -un | xargs)"
check "firewall (UFW) is active"              grep -q 'Status: active' <<<"$status"
check "firewall opens only ports: $want (open: ${open:-none})" test "$open" = "$want"

# --- Updates ----------------------------------------------------------------------
# Security updates are what matters (and what unattended-upgrades installs daily).
# Other repos (e.g. Docker) release new versions at any time - not a failure.
pending="$(apt-get -s upgrade 2>/dev/null | grep '^Inst' | grep -c -- '-security')"
check "no pending security updates ($pending pending)" test "$pending" -eq 0

# --- Services for this server's role ----------------------------------------------
case "$ROLE" in
  lb)
    check "nginx (load balancer) is running"  systemctl is-active --quiet nginx ;;
  web)
    check "Docker is running"                 systemctl is-active --quiet docker
    check "frontend container answers /health" curl -sf -m 5 http://127.0.0.1/health ;;
  app)
    check "Docker is running"                 systemctl is-active --quiet docker
    check "backend container answers /health" curl -sf -m 5 http://127.0.0.1:3000/health ;;
  cicd)
    check "Docker is running"                 systemctl is-active --quiet docker
    check "Jenkins is running"                systemctl is-active --quiet jenkins ;;
esac

# --- Bonus features ------------------------------------------------------------------
if [[ "$BONUS" == "true" ]]; then
  check "Fail2Ban is running"                 systemctl is-active --quiet fail2ban
  if [[ "$ROLE" == "backup" ]]; then
    check "daily backup timer is active"      systemctl is-active --quiet backup-pull.timer
    fresh="$(find /srv/backups -name '*.tar.gz' -mtime -2 2>/dev/null | wc -l)"
    check "recent backups exist ($fresh archives from the last 2 days)" test "$fresh" -ge 5
  fi
fi
