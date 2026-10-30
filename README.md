# Automation Alchemy
This project rebuilds **all of it as code**, and adds a CI/CD server whose pipeline
tests, builds, publishes and deploys every Git commit and rolls back on its own
when a deploy goes wrong.

**One command builds everything from an empty laptop no manual steps.**

```powershell
.\scripts\up.ps1 -Fresh
```

| | |
|---|---|
| App | <http://localhost:8080> (or <http://192.168.56.10>) |
| Jenkins | <http://192.168.56.14:8080> (user `admin`, password in the vault) |
| Validate | `bash scripts/validate.sh` (Git Bash) — 108 checks, 140 with `--bonus` |

More detail:
- [docs/architecture_project-3.md](docs/architecture_project-3.md) — diagrams: VMs, network, pipeline, rollback, backups
- [docs/notes_project-3.md](docs/notes_project-3.md) — design decisions, real incidents and how they were fixed

---

## 1. What gets built

| VM | IP | Role | Open ports (UFW) |
|---|---|---|---|
| `load-balancer` | 192.168.56.10 | nginx, `least_conn` over both web servers | 22, 80 (host port 8080 → 80) |
| `web-server-1` | 192.168.56.11 | frontend container | 22, 80 from the LB only |
| `web-server-2` | 192.168.56.12 | frontend container | 22, 80 from the LB only |
| `app-server` | 192.168.56.13 | backend container (API) | 22, 3000 from the web servers only |
| `cicd-server` | 192.168.56.14 | Ansible control node + Jenkins + Docker | 22, 8080 from the admin laptop only |
| `backup-server` *(bonus)* | 192.168.56.15 | pulls a daily backup from every VM | 22 |

SSH (port 22) is only accepted from the admin laptop (192.168.56.1) and from
cicd-server (and the backup server, in bonus mode).

**Every VM gets:** all security patches, daily automatic security updates,
a `devops` user with a sudo password, SSH with key only (no root, no passwords,
`AllowUsers devops`), umask `0027`, a deny-by-default firewall, static IP,
hostname and `/etc/hosts` entries for all other VMs.

**The app** is the Python (FastAPI) frontend + backend from Project 2, packaged as
Docker images on Docker Hub (`zeek14/alchemy-frontend`, `zeek14/alchemy-backend`).
The page shows live server metrics and the running version.

## 2. Tools

| Tool | Used for |
|---|---|
| **Vagrant** + VirtualBox | creates the VMs — reads the VM list from the Ansible inventory |
| **Ansible** (roles, Vault) | everything inside the VMs: patches, hardening, firewall, Docker, app, nginx, Jenkins |
| **Jenkins** (LTS, JCasC, Job DSL) | the CI/CD pipeline — configured 100 % as code, no clicks |
| **Docker** / Docker Hub | app images, tagged with the Git commit ID |
| Ruff, Bandit, pytest | lint, code security scan, unit tests |
| Trivy | image vulnerability scan (quality gate) |
| k6 | load test after every deploy |
| Slack | build / deploy / rollback notifications |
| GitHub Actions *(bonus)* | the same code checks + ansible-lint + shellcheck in the cloud |
| Fail2Ban *(bonus)* | bans IPs after repeated failed SSH logins |

## 3. Prerequisites (Windows laptop)

- VirtualBox 7.x and Vagrant 2.4+
- OpenSSH client (`ssh`, `ssh-keygen`) — built into Windows 10/11
- Git Bash (for `validate.sh`)
- About 8 GB free RAM (the 5 core VMs use 6.5 GB; the bonus VM adds 0.5 GB)
- The file **`.vault_pass`** in the repo root, containing the Ansible Vault password.
  It is never committed — it is handed over separately.

The SSH key pair in `keys/` is generated automatically on the first run.

## 4. Run it

All commands from the repo folder.

| What | Command (PowerShell) | Time |
|---|---|---|
| Build everything from a blank slate | `.\scripts\up.ps1 -Fresh` | 35–90 min (mostly downloads) |
| Same, with the bonus features | `.\scripts\up.ps1 -Fresh -Bonus` | 40–90 min |
| Start existing VMs (after a shutdown) | `.\scripts\up.ps1` | ~2 min |
| Shut everything down cleanly | `.\scripts\down.ps1` | ~1 min |
| Delete all VMs | `.\scripts\down.ps1 -Destroy` | ~1 min |

What `up.ps1 -Fresh` does:
1. Checks the prerequisites, destroys old VMs, forgets old SSH host keys.
2. `vagrant up` creates the VMs. `vagrant/bootstrap.sh` only creates the `devops` user
   (and, on cicd-server, installs Ansible) — the only shell provisioning in the project.
3. cicd-server is created **last** and runs `ansible/site.yml`, which configures **all** VMs:
   patches → hardening → firewall → Docker → first image build → app deploy → load balancer → Jenkins.
4. Jenkins starts already configured (credentials + both jobs), polls Gitea, and deploys the
   newest commit by itself.

## 5. Check it

```bash
bash scripts/validate.sh            # 5 core VMs: 108 checks
bash scripts/validate.sh --bonus    # + backup server and Fail2Ban: 140 checks
```

Read-only. For each VM it checks hostname, IP, name resolution, sudo, umask, SSH policy,
firewall (exactly the expected ports), pending security updates and the role's services.
From the laptop it proves that root and password logins are refused, the app answers
through the load balancer, requests are spread over both web servers, and the web/app
servers can **not** be reached directly.

Idempotency run the full setup again; the second run reports `changed=0`
(only new Ubuntu patches can show up as changes):

```bash
ssh -i keys/ansible_key devops@192.168.56.14       # Git Bash, then on cicd-server:
cd ~/automation-alchemy/ansible && ansible-playbook site.yml
```

## 6. The pipeline

Jenkins checks Gitea every minute. For each new commit:

| # | Stage | Fails the build when |
|---|---|---|
| 1 | Version | — image tag = short commit ID; the live version is recorded for rollback |
| 2 | Code checks | Ruff lint error, Bandit finding, or a failing unit test |
| 3 | Build images | Docker build fails |
| 4 | Image scan | Trivy finds a **CRITICAL** vulnerability that has a fix |
| 5 | Push to Docker Hub | push fails 3 times (retried); `build-info.txt` is archived |
| 6 | Deploy | Ansible `deploy.yml`: backend, then the web servers **one at a time** |
| 7 | Smoke test | 6 requests through the LB: all 200, new version shown, both web servers used |
| 8 | Load test | k6, 5 users × 20 s: > 1 % errors or p95 > 2.5 s |

**Results:**
- Fails in stages 1–5 → nothing was deployed. Slack: ⛔ *Blocked*.
- Fails in stages 6–8 → **automatic rollback** to the version that was live before. Slack: ↩️ *Rolled back*.
- Success → Slack: ✅ *Deployed*.

**Manual rollback:** Jenkins job `automation-alchemy-rollback` → *Build with Parameters* →
`VERSION` = any earlier commit ID (or `initial`). It deploys that image and smoke-tests it.

**Artifacts:** each build stores `build-info.txt` (commit, time, exact image digests)
and the unit test results (Jenkins *Tests* tab).

## 7. Secrets

All secrets live in `ansible/group_vars/all/vault.yml`, encrypted with Ansible Vault (AES-256):
the devops password, Docker Hub token, Jenkins admin password and Slack webhook.

- `.vault_pass` and `keys/` are in `.gitignore` and never committed.
- Jenkins gets the secrets as **credentials** created by JCasC from files only Jenkins can read;
  the pipeline log shows them as `****`.
- Ansible tasks that handle secrets use `no_log: true`.

To view or change a secret:
```bash
ansible-vault edit ansible/group_vars/all/vault.yml --vault-password-file .vault_pass
```

## 8. Bonus features

| Feature | How | Check |
|---|---|---|
| Backup server | Pull model: backup-server pulls a `tar.gz` of `/etc` (+ Jenkins home) from every VM daily at 02:00 (systemd timer), keeps 7 days. Its key can run **only** the export command (`command=…,restrict`). | `ls /srv/backups/*` on backup-server |
| Restore | Copy an archive to the VM and unpack only what you need, e.g. `sudo tar -xzf web-server-1-<date>.tar.gz -C / etc/nginx` | `tar -tzf <archive>` lists the contents |
| Fail2Ban | SSH jail on every VM, bans via UFW (5 failures / 10 min → 10 min ban). The admin laptop is whitelisted. | `sudo fail2ban-client status sshd` |
| GitHub Actions | lint + security + unit tests, `ansible-lint` (production profile), `shellcheck` on every push | GitHub → *Actions* tab |
| Automatic rollback | see the pipeline section | Slack ↩️ |
| Load test, image scan, Slack | see the pipeline section | |

Demonstrate a ban without locking yourself out:
```bash
sudo fail2ban-client set sshd banip 203.0.113.7
sudo fail2ban-client status sshd
sudo ufw status | grep 203.0.113.7
sudo fail2ban-client set sshd unbanip 203.0.113.7
```

## 9. Repository layout

```
Vagrantfile               VMs, read from the Ansible inventory
vagrant/bootstrap.sh      creates 'devops' (+ installs Ansible on cicd-server)
ansible/
  inventory/hosts.yml     single source of truth: hosts, IPs, RAM, CPUs
  site.yml                the whole infrastructure (idempotent)
  deploy.yml              app deploy only (used by Jenkins and rollback)
  group_vars/             settings per group + encrypted vault.yml
  roles/                  common, hardening, firewall, docker, image_build, app_deploy,
                          loadbalancer, jenkins, fail2ban, backup_server, backup_source
app/                      frontend + backend source, Dockerfiles, unit tests
Jenkinsfile               the main pipeline
ci/                       pipeline helpers: code checks, rollback job, Slack, k6 test
scripts/                  up/down (one click), validate, smoke test, sync to cicd
.github/workflows/ci.yml  GitHub Actions checks
docs/                     architecture and project notes
```

## 10. Review checklist

1. `.\scripts\up.ps1 -Fresh` — wait for *Ready*.
2. `bash scripts/validate.sh` — expect `ALL 108 CHECKS PASSED`.
3. Open <http://localhost:8080>. Load balancing: run `curl -sI http://192.168.56.10 | grep X-Upstream`
   a few times — the answer alternates between `192.168.56.11:80` and `192.168.56.12:80`.
4. Jenkins → `automation-alchemy` — the first build ran by itself and is green.
5. Push a small change (e.g. the heading in `app/frontend/templates/index.html`) →
   new build → new version on the page → Slack ✅.
6. Push a broken change → quality gate blocks it (Slack ⛔), or the deploy is rolled back (Slack ↩️).
7. Re-run `ansible-playbook site.yml` on cicd-server → `changed=0`.
8. `.\scripts\down.ps1` then `.\scripts\up.ps1` → everything comes back by itself.
9. *(bonus)* `.\scripts\up.ps1 -Fresh -Bonus`, then `bash scripts/validate.sh --bonus` → 140 checks.
