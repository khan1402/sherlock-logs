# Review guide — Sherlock Logs

Short, simple answers for every review question, with the files to show and the demo
commands. Terminals: **Git Bash** = the laptop, in the repo folder. **cicd-server** = after
`ssh -i keys/ansible_key devops@192.168.56.14` and `cd ~/sherlock-logs/ansible`.

Before the review:
- Keep the laptop awake (sleep pauses the VMs).
- `bash scripts/validate.sh --bonus` → `ALL 209 CHECKS PASSED`.
- Open Grafana (<http://192.168.56.16:3000>), Kibana (<http://192.168.56.16:5601>),
  Prometheus (<http://192.168.56.16:9090/targets>) and Slack.
- Grafana password (cicd-server): `ansible-vault view group_vars/all/vault.yml | grep grafana`

---

## Part 1 — Concepts

### Push-based vs pull-based monitoring
In a **pull** model, the monitoring server asks each machine for its numbers on a schedule.
In a **push** model, each machine sends its data by itself. In this project, **metrics are
pulled**: Prometheus asks every VM every 15 seconds, so a VM that stops answering shows up
at once as DOWN. **Logs are pushed**: Filebeat on every VM sends new log lines to Logstash
as they are written, because logs come all the time and must not be lost.

### Architecture of the ELK stack
ELK = **Elasticsearch**, **Logstash** and **Kibana**, plus **Filebeat** as the shipper.
Filebeat reads the log files on every VM and sends them to Logstash. Logstash parses each
line into fields and stores it in Elasticsearch, which saves and indexes the logs (in this
project on 2 nodes, every log stored twice). Kibana is the web page to search the logs and
build dashboards.

### Prometheus vs Nagios or Zabbix
Prometheus is built for modern, changing systems: it stores **time series** (numbers over
time) with labels, has a powerful query language (**PromQL**) for graphs and alerts, and
pulls metrics over simple HTTP. Exporters exist for almost everything, and it fits Docker
well. The downsides: it is for **metrics only** (logs need ELK), long-term storage needs extra
tools, and alerting and dashboards come from other tools (here Grafana). Nagios is mainly
up/down checks; Zabbix is a full suite with agents, but heavier and less flexible to query.

### Adjusting the scrape interval
The scrape interval is how often Prometheus collects metrics. In this project it is **15 s**,
set in `ansible/roles/monitoring/defaults/main.yml`, line 17 (`monitoring_scrape_interval`).
To change it, edit the value (e.g. `30s`) and run on cicd-server:
`ansible-playbook site.yml --tags monitoring -e enable_bonus=true`. Shorter = fresher data but
more load and disk; longer = lighter but slower alerts.

### Node Exporter and cAdvisor — and common issues
**Node Exporter** gives the VM's metrics (CPU, memory, disk, network), on port 9100 of every
VM. **cAdvisor** gives each container's metrics, on port 8081 of every Docker VM. Show:
`ansible/roles/node_exporter/`, `ansible/roles/cadvisor/tasks/main.yml`, and the targets page.

Common issues, in the order to check them: the **exporter is stopped** (target error
"connection refused" → start the service), the **firewall blocks** Prometheus (timeout →
check `ufw status`, re-apply `--tags firewall`), the **VM is down** ("no route to host" →
start the VM), the **target is missing** from the config (add the VM to the inventory, re-run
the monitoring tag), or all targets are UP but **Grafana is empty** (time range, filter, or
no traffic).

### Grafana vs Kibana or Datadog
**Grafana** is best for **metrics**: fast time-series graphs, many data sources, and built-in
alerting to Slack. **Kibana** is best for **logs**: full-text search and log dashboards on
Elasticsearch. **Datadog** does both as a paid cloud service. In this project, Grafana shows
metrics and sends alerts, Kibana shows logs — each tool for what it does best, all free and
self-hosted.

---

## Part 2 — The application

### Prometheus client libraries
The app uses the **prometheus_client** Python library. It creates metric objects in the code
(Counter, Histogram) and serves them on a `/metrics` page in the Prometheus text format;
Prometheus scrapes that page every 15 s. Request count and response time are measured for
every request.

### At least one custom metric
In this project there are two:
- `metrics_collect_seconds` — a **Histogram** in `app/backend/main.py`, line 41: how long the
  backend takes to collect the system facts.
- `frontend_backend_errors_total` — a **Counter** in `app/frontend/main.py`, line 46, increased
  at line 92 every time the frontend can't reach the backend.

Show them in Grafana → Application Performance → *Custom application metrics*.

### Logs to Logstash — format inconsistencies and parsing errors
The app writes **JSON** logs (`app/*/logging_setup.py`), so every line has the same fields.
Filebeat sends them to Logstash, which uses the right parser per log type: `json` for the
app, `grok` with two patterns for system logs (both timestamp styles), `COMBINEDAPACHELOG`
for nginx, and `date` for the time. A line that can't be parsed is **never dropped**: it is
stored with a tag like `_syslog_parse_failure`. In Kibana, `tags : *_failure` finds them —
0 results means everything is parsed. File: `ansible/roles/monitoring/templates/logstash/logstash.conf.j2`.

---

## Part 3 — Dashboards

### Grafana: data sources, filter and aggregate
All 3 dashboards use **Prometheus** as the data source. Each panel has a PromQL query.
A query **filters** with labels, like `instance="web-server-1"`, or with the VM / Container
dropdowns at the top. It **aggregates** with functions like `sum`, `avg by (instance)` and
`rate`, which turn many lines into one per VM or service.

Demo: VM Performance → pick one VM in the dropdown (filter). Then Explore → Builder →
metric `node_memory_MemAvailable_bytes` → shows 7 lines; add a label filter `instance =
app-server` → 1 line; remove it and add Operations → Aggregations → **Sum** → 1 line with the
total. Code mode, free memory in GB: `node_memory_MemAvailable_bytes / 1024^3`.

### Kibana: search and filtering
Kibana has 3 dashboards: **System Logs**, **Application Logs**, **Docker Logs**. To analyse logs:
the **search bar** (KQL), the **time picker**, and **clicking a chart** to add a filter.
Examples: `agent.name:"web-server-1"`, `container.name:"backend"`, `stream:"stderr"`,
`app.status:200`. Demo: `ssh wronguser@192.168.56.11` (Git Bash), then System Logs →
search `system.message:"Invalid user"` → the *Failed SSH logins per VM* panel shows web-server-1.

---

## Part 4 — Operations

### Real-time metrics and troubleshooting metric collection
Prometheus collects every 15 s, so a change shows up within 15–30 s. When metrics are
missing, start at the **targets page**: the error tells where to look (see *Node Exporter and
cAdvisor* above). Optional demo, on cicd-server:

```bash
ansible web-server-1 -b -m systemd -a "name=node_exporter state=stopped"   # target goes DOWN
ansible web-server-1 -b -m systemd -a "name=node_exporter state=started"   # back UP
```

### Historical data and retention
Old data is deleted automatically, so the disk never fills. All values are in
`ansible/roles/monitoring/defaults/main.yml`: metrics for **15 days or 5 GB** (lines 21–22),
logs for **14 days** through an Elasticsearch **ILM policy** (line 57). To keep data longer,
change the numbers and run the monitoring tag; Ansible updates Prometheus and
Elasticsearch. To see history: set the time picker in Grafana or Kibana to *Last 7 days*.

### The monitoring VM in the automation flow
The monitoring VM is one entry in `ansible/inventory/hosts.yml`. Vagrant reads that file and
creates it with the other VMs; `site.yml` gives it the same baseline (patches, hardening,
firewall, Docker) and then the play **Monitoring stack** installs Prometheus, Grafana and ELK.
In this project, monitoring and logging share this one VM.

### CI/CD deploys the agents, with dynamic configuration
Jenkins has a **Monitoring agents** stage (`Jenkinsfile`, line 147) that runs
`monitoring-agents.yml` on every build. The configs are built from the inventory:
cAdvisor only on `docker_hosts`; `filebeat.yml.j2` adds container logs only on Docker VMs
(line 29) and nginx logs only on the load balancer (line 49); the Logstash address is the
variable `monitoring_ip` (`group_vars/all/vars.yml`, line 37), not a fixed IP. For a new VM or
environment, only the inventory changes. The **Monitoring check** stage (line 155) stops the
deploy if monitoring is broken.

---

## Part 5 — Alerts

### Thresholds and alert fatigue
Alert fatigue = so many alerts that people stop reading them. In this project: sensible
thresholds (CPU 80 %, memory 90 %, disk 20 % free), a **wait time** so short spikes are ignored
(5 min for CPU and memory), **grouping** so one problem gives one Slack message, a reminder
only every **4 hours**, and a **Resolved** message at the end. Settings:
`defaults/main.yml`, lines 74–76 and the rules from line 97.

### Logstash filters: parse and match
Everything is in `logstash.conf.j2`. **input** (lines 19–23) receives logs from Filebeat.
**filter** (lines 25–120) parses and checks them: `grok` (lines 35–43, 85–88) cuts text into
fields, `date` (47–52) sets the real time, `json` (62–66) reads the app logs, `mutate` adds
fields and tags, and `if` checks conditions. The **alert patterns** (lines 94–106) tag a failed
SSH login or an app error; **throttle** (111–119) allows one Slack message per VM and type
every 5 minutes. **output** (122–145) stores everything in Elasticsearch and sends tagged lines
to Slack. The result is visible in Kibana: each log line split into fields.

Another example: a payment log `2026-11-12 12:00:01 ERROR Payment failed user=42 amount=19.99`
→ grok extracts level, user and amount → `if [level] == "ERROR" and [text] =~ /Payment failed/`
adds an alert tag → the output sends it to Slack.

### Fine-tuning thresholds to reduce false positives
Look at the normal values on the dashboards first, set the threshold above them, add a
wait time (`for`), use averages over time (`rate(...[5m])`) instead of single values, and
skip things that don't matter (temporary filesystems, Java containers that always sit near
their limit). Change `threshold` / `for` in `defaults/main.yml` and run the monitoring tag.

---

## Part 6 — Alert tests (Git Bash)

Run one test at a time. Start the 5-minute tests early and answer other questions meanwhile.

**CPU above 80 % for 5 minutes** — `bash scripts/demo/cpu.sh web-server-1`. stress-ng runs on all
cores for 6 minutes. Grafana → VM Performance shows ~100 %; the rule goes Pending, then Firing;
Slack after ~6 min, Resolved after the load ends.

**Disk below 20 % free** — `bash scripts/demo/disk.sh web-server-1`. fallocate creates a big file
until ~15 % is free. Slack after ~2 min. Clean up: `bash scripts/demo/disk.sh web-server-1 stop`.

**Memory above 90 % for 5 minutes** — `bash scripts/demo/memory.sh web-server-1`. stress-ng fills
memory to ~95 % (size calculated on the VM, so it can't crash it). Slack after ~6 min; the
critical *High CPU and low memory together* alert also fires after ~2 min.

**Container restarts more than 3 times in 15 minutes** —
`bash scripts/demo/container-restarts.sh web-server-1`. It runs
`docker run --restart=always --name test_container ubuntu:22.04 bash -c "sleep 10; exit 1"`.
Slack after ~3–4 min. Clean up: `bash scripts/demo/container-restarts.sh web-server-1 stop`.
The count falls back to 0 within 15 minutes.

**Container memory above 80 % of its limit** — `bash scripts/demo/container-memory.sh web-server-1`.
A container with a 128 MB limit uses 110 MB. Docker Containers → *Memory vs limit*; Slack after
~2–3 min. Clean up: `bash scripts/demo/container-memory.sh web-server-1 stop`.

**VM unreachable** — `bash scripts/demo/vm-down.sh web-server-1` (or `... 300` for 5 minutes).
It switches off the VM's project network card (like `ifconfig down`) and turns it back on by
itself, because a plain `ifconfig down` would cut the SSH session for good. Show
`ping -c 3 192.168.56.11` on cicd-server (100 % loss), the targets page (DOWN), and Slack.

**Elasticsearch yellow** — `bash scripts/demo/es-yellow.sh`. It stops es02: the replicas have
nowhere to live, so the cluster turns yellow (data still complete on es01). Slack after
~2 min. See it in Grafana Explore (`elasticsearch_cluster_health_status` — the line with
`color="yellow"` is at 1) or Kibana Dev Tools (`GET _cluster/health`). Restore:
`bash scripts/demo/es-yellow.sh restore` — green again a few minutes later.

**Pending vs Firing:** Pending = the problem was seen and the rule waits its `for` time.
Firing = it lasted the whole wait time; Slack gets the message.

---

## Part 7 — Quality

### Advanced alert rules with PromQL
Normal alerts check one value now. Advanced ones look at **trends** or **combinations**
(`defaults/main.yml`, lines 192–240):
- `predict_linear(free disk[1h], 4h) < 0` — the disk will be full within 4 hours.
- `deriv(CPU[30m])` — CPU is climbing steadily, before it reaches 80 %.
- `(CPU > 80) and on (instance) (free memory < 10 %)` — both on the same VM = critical.
- failed requests ÷ all requests > 5 % — application error rate.

### Notification throttling and escalation
**Throttling:** grouping per alert type and VM, 30 s group wait, 5 min group interval, a
reminder only every 4 hours, and Logstash's 5-minute throttle. **Escalation:** every alert has
a severity (info, warning, critical), shown at the end of the Slack title. In this project
all go to one Slack channel; a bigger team would route critical alerts to an on-call tool
with shorter reminders. Files: `templates/grafana/alerting/contact-points.yml.j2`, lines 23–29.

### Extras beyond the core
A 2-node Elasticsearch cluster, the Elasticsearch exporter with its own alerts, advanced
trend and combination alerts, log-pattern alerts from Logstash, dashboards as code, a
monitoring health check in Jenkins, retention policies, a demo script for every test,
`validate.sh` with 209 checks, plus the backup server and Fail2Ban. Security: all secrets in
Ansible Vault, the Slack webhook never written in config files, monitoring ports open only
to the monitoring server, Elasticsearch on loopback only, and Trivy image scans.
