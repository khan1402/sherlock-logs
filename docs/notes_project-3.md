# Project notes — Automation Alchemy

Why things are built the way they are, what went wrong while building it, and how
each problem was fixed. For the overview see the [README](../README.md); for diagrams see
[architecture_project-3.md](architecture_project-3.md).

---

## 1. Key design decisions

| Decision | Why |
|---|---|
| **One inventory file** (`ansible/inventory/hosts.yml`) feeds Vagrant, Ansible, nginx, the firewall and `/etc/hosts` | An IP or hostname is written once. Adding a third web server is one inventory entry. |
| **cicd-server is the Ansible control node** | Windows can't run Ansible natively. cicd-server needs Ansible anyway, for Jenkins deploys. |
| **Shell provisioning only in `bootstrap.sh`**, and only to create `devops` | Everything else is Ansible, so it is idempotent and readable as one system. |
| **Image tag = Git commit ID** | Every running container traces back to one exact commit. No "latest" confusion. |
| **Rollback target = the version live on `/health`** before the deploy | No database of releases needed. The truth is whatever users see right now. |
| **Rolling deploy** (`serial: 1`) + health check per server | One web server always serves users, so there is no downtime. |
| **`network_mode: host`** for the containers | Docker's published ports write iptables rules that **bypass UFW**. With host networking, UFW stays in control. |
| **Sudo needs a password** (bootstrap's passwordless sudo is removed) | A stolen SSH key alone is not root. Ansible gets the password from the vault. |
| **Jenkins 100 % as code** (JCasC + Job DSL) | A rebuilt Jenkins is identical. Clicked changes would be lost and can't be reviewed. |
| **Pipeline tools run as throwaway containers** (Python, Trivy, k6) | Nothing extra is installed on the CI server, and versions are the same on every run. |
| **Trivy gate: CRITICAL with a fix available** | Unfixable CVEs would block every build with nothing to do about them. HIGH is reported, not blocking. |
| **Polling Gitea every minute** instead of a webhook | The VMs are on a private network that Gitea can't reach. GitHub is only a mirror for GitHub Actions. |
| **Backups: pull, not push** | Only the backup server holds a key, and that key can run one command. A hacked server can't touch the backups. |
| **Fail2Ban whitelists the admin IP** | The validation script makes failed logins on purpose (it proves root and password logins are refused). |

## 2. Incidents and fixes

Each one happened for real during the build. They're listed in order.

### 1. cicd-server hung at boot with 2 vCPUs
- **Problem:** with 2 vCPUs, cicd-server froze during boot. The laptop runs VirtualBox next to Hyper-V/WSL2.
- **Fix:** 1 vCPU (`vm_cpus: 1` in the inventory) and 1 Jenkins executor. Builds are sequential anyway (`disableConcurrentBuilds`).

### 2. Provisioning froze at "Turn the firewall on"
- **Problem:** enabling UFW while Ansible had open SSH connections dropped them (connection tracking). The run hung forever.
- **Fix:** a first play in `site.yml` turns on **cicd-server's own firewall before** Ansible connects to any other VM. The NAT gateway 10.0.2.2 is allowed for SSH on cicd-server, so Vagrant can still reach it.

### 3. SSH refused after every rebuild
- **Problem:** rebuilt VMs get new host keys on the same IPs, so SSH warned "REMOTE HOST IDENTIFICATION HAS CHANGED".
- **Fix:** `up.ps1` runs `ssh-keygen -R` for .10–.15 automatically.

### 4. Vagrant can't start hardened VMs
- **Problem:** after hardening, only `devops` may log in (`AllowUsers devops`), so `vagrant up` can't confirm that an existing VM booted. `/vagrant` is also no longer mounted.
- **Fix:** `up.ps1` starts existing VMs directly with `VBoxManage startvm --type headless`. `sync-to-cicd.sh` mounts `/vagrant` again when needed.

### 5. Docker Hub login failed and the reason was hidden
- **Problem:** a wrong Docker Hub username in the vars. The task had `no_log: true` (correct, it handles the token), so the error message was hidden too.
- **Fix:** `block` / `rescue` around the login. The rescue prints a clear message with the username and the error, but never the token.

### 6. The quality gate caught real bugs
- **Problem:** build #7 failed on Ruff lint errors. Later, a mis-indented `return` (under `except`) made the frontend show `null` instead of the page.
- **Fix:** the code was fixed. The pipeline did its job: broken code never reached the servers. Unit tests now cover the frontend's error path.

### 7. Root-owned files broke the sync
- **Problem:** the code-check container wrote `reports/` as root, and `rsync` couldn't overwrite it.
- **Fix:** the container runs as the Jenkins user (`--user`), and `reports/` is in `.gitignore` and excluded from the sync.

### 8. Secrets were exposed outside the vault
- **Problem:** during setup, the devops password and the Slack webhook URL were shown in plain text outside the vault.
- **Fix:** both were **rotated** immediately, and the shell history was cleared. Rules since then: secrets are only typed into `ansible-vault edit` or `read -rs`, and never pasted into chats, tickets or commits.

### 9. Jenkins sometimes started without the rollback job
- **Problem:** after a restart, JCasC created one job but not the other.
- **Fix:** the jenkins role checks every expected job through the API after each start. If one is missing, it requests a CSRF crumb, POSTs a JCasC reload, and checks again. The fresh rebuilds after this fix created both jobs on the first try.

### 10. GitHub Actions failed on YAML whitespace
- **Problem:** the first GitHub Actions run failed `ansible-lint`: 29 trailing-space and end-of-file errors in files from early in the project.
- **Fix:** a one-time cleanup (whitespace only, verified with `git diff --ignore-all-space`), and VS Code now trims on save (`.vscode/settings.json`).

### 11. First build on a fresh server failed on network errors
- **Problem:** Docker Hub reset the connection during a layer push, and a DNS lookup for Slack timed out. All quality gates had passed. Only the network failed.
- **Fix:** the push is retried up to 3 times (repeating a push is safe, uploaded layers are skipped), and the Slack call uses `curl --retry 3`. The next build went green.

### 12. Validation vs. reality
- **Problem 1:** `validate.sh` deliberately tries root and password logins. With Fail2Ban on, a few validate runs in 10 minutes would ban the admin laptop.
  **Fix:** the admin IP is in Fail2Ban's `ignoreip`. A ban is demonstrated with a fake IP instead.
- **Problem 2:** a validate run hours after a build found a pending security update (`libarchive13`), released after the build.
  **Fix:** none needed, the check was right. Re-running `site.yml` applied it, and unattended-upgrades would install it within a day. The check now counts **security** updates only, so a new Docker release doesn't fail it.
- **Problem 3:** that check showed `docker.list: Permission denied`. The hardening umask `0027` made the apt repo files Ansible creates readable by root only.
  **Fix:** explicit `mode: "0644"` on the Docker and Jenkins repo files.
- **Problem 4:** once, SSH from the laptop to the core VMs failed during a single validate run. It never happened again in later runs, and the cause is unknown.
  **Fix:** `validate.sh` now prints the real SSH error instead of hiding it.

### 13. Gitea push fails on the first try
- **Problem:** pushing to the school Gitea often fails authentication once, then works on retry.
- **Fix:** retry the push, or use a Gitea personal access token. Jenkins reads Gitea with its own read-only token, so the pipeline isn't affected.

## 3. Tested results

| Test | Result |
|---|---|
| Blank slate: `up.ps1 -Fresh` | ready in 33 min, `failed=0` on all VMs, no manual steps |
| Blank slate with bonus: `up.ps1 -Fresh -Bonus` | ready in 88 min (slow mirrors that day), `failed=0` on 6 VMs |
| `validate.sh` | 108 / 108 core, 140 / 140 with `--bonus` (twice in a row) |
| Idempotency: `site.yml` second run | `changed=0`; only new Ubuntu patches show up as changes |
| Reboot: `down.ps1` + `up.ps1` | app back in 1.6 min, same version, 108 / 108 |
| Quality gate | broken code stopped before deploy (Slack ⛔) |
| Automatic rollback | broken deploy replaced by the previous version (Slack ↩️) |
| Manual rollback job | chosen version deployed and smoke-tested (Slack ↩️) |
| First build on a fresh Jenkins | ran by itself and deployed the newest commit |
| GitHub Actions | 4 / 4 jobs green |

## 4. Known limits and warnings

- **HTTP only.** No TLS on the load balancer or Jenkins. Acceptable on a private host-only network; in production it would get certificates.
- **One app-server.** The backend is a single point of failure. The frontend is redundant, the backend isn't.
- **Jenkins runs builds on the built-in node.** Jenkins warns about this. A separate build agent would be the production setup.
- **Other Jenkins notices:** a future Java support notice and a Content Security Policy notice. They don't affect the pipeline.
- **cicd-server is not rebooted** after kernel updates during provisioning, because it is running Ansible. "System restart required" is expected. The next `down.ps1` / `up.ps1` applies it.
- **Ubuntu 22.04** is used because it's the project's base box. Its standard support ends in 2027.
- **Trivy and k6 use `:latest`**, so the vulnerability database is always current. Production would pin versions.
- **Build time depends on the network.** Ubuntu and Docker mirrors decide whether a blank-slate build takes 35 or 90 minutes.
