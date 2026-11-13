#!/usr/bin/env python3
"""
build-dashboards.py - the SOURCE of all 6 dashboards (dashboards as code).

  python3 scripts/build-dashboards.py

Writes (into the monitoring role, where Ansible picks them up):
  ansible/roles/monitoring/files/grafana-dashboards/vm-performance.json
  ansible/roles/monitoring/files/grafana-dashboards/docker-containers.json
  ansible/roles/monitoring/files/grafana-dashboards/app-performance.json
  ansible/roles/monitoring/files/kibana/dashboards.ndjson

Why a script instead of hand-written JSON: Grafana and Kibana store
dashboards as long, repetitive JSON. Here every panel is ONE readable line
(title, query, unit, position), the helpers fill in the boilerplate, and every
panel gets the same structure. To change a dashboard: edit this file, run it,
commit the script AND the generated files.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = os.path.join(ROOT, "ansible", "roles", "monitoring", "files")
J = json.dumps


def pretty(o, ind=0, width=110):
    """JSON with small objects on one line - readable diffs in Git."""
    s = json.dumps(o, ensure_ascii=False)
    if len(s) + ind <= width or not isinstance(o, (dict, list)) or not o:
        return s
    pad = " " * (ind + 2)
    if isinstance(o, dict):
        items = [f"{pad}{json.dumps(k)}: {pretty(v, ind + 2, width)}" for k, v in o.items()]
        return "{\n" + ",\n".join(items) + "\n" + " " * ind + "}"
    items = [pad + pretty(v, ind + 2, width) for v in o]
    return "[\n" + ",\n".join(items) + "\n" + " " * ind + "]"


# =====================================================================================
# GRAFANA (Prometheus queries)
# =====================================================================================
DS = {"type": "prometheus", "uid": "prometheus"}


# Threshold colours: green below the first value, then orange, then red.
def steps(orange, red):
    return [{"color": "green", "value": None}, {"color": "orange", "value": orange}, {"color": "red", "value": red}]


def ts(title, exprs, unit, x, y, w=12, h=8, desc="", maxv=None):
    p = {
        "type": "timeseries", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit, "custom": {"fillOpacity": 10, "showPoints": "never"}},
                        "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": [{"refId": chr(65 + i), "expr": e, "legendFormat": legend}
                    for i, (e, legend) in enumerate(exprs)],
    }
    if maxv is not None:
        p["fieldConfig"]["defaults"]["min"] = 0
        p["fieldConfig"]["defaults"]["max"] = maxv
    return p


def stat(title, expr, unit, x, y, w=6, h=4, desc="", thresholds=None, legend=""):
    return {
        "type": "stat", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": thresholds or [
            {"color": "green", "value": None}]}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"},
        "targets": [{"refId": "A", "expr": expr, "legendFormat": legend, "instant": True}],
    }


def bargauge(title, expr, unit, legend, x, y, w=12, h=8, desc="", maxv=100):
    return {
        "type": "bargauge", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit, "min": 0, "max": maxv, "thresholds": {"mode": "absolute", "steps": [
            {"color": "green", "value": None}, {"color": "orange", "value": 70}, {"color": "red", "value": 85}]}},
            "overrides": []},
        "options": {"orientation": "horizontal", "displayMode": "gradient",
                    "reduceOptions": {"calcs": ["lastNotNull"]}},
        "targets": [{"refId": "A", "expr": expr, "legendFormat": legend, "instant": True}],
    }


def table(title, exprs, x, y, w=24, h=8, desc=""):
    return {
        "type": "table", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {"showHeader": True},
        "targets": [{"refId": chr(65 + i), "expr": e, "format": "table", "instant": True} for i, e in enumerate(exprs)],
        "transformations": [{"id": "merge", "options": {}},
                            {"id": "organize", "options": {"excludeByName": {"Time": True}}}],
    }


def row(title, y):
    return {"type": "row", "title": title, "collapsed": False,
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}


def var(name, label, query):
    return {"name": name, "label": label, "type": "query", "datasource": DS,
            "query": {"query": query, "refId": "V"}, "definition": query,
            "refresh": 2, "includeAll": True, "multi": True, "allValue": ".*",
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]}, "sort": 1}


def dashboard(uid, title, desc, panels, variables, tags):
    for i, p in enumerate(panels, 1):
        p["id"] = i
    return {"uid": uid, "title": title, "description": desc, "tags": tags, "editable": False,
            "timezone": "browser", "refresh": "30s", "time": {"from": "now-1h", "to": "now"},
            "schemaVersion": 39, "version": 1, "templating": {"list": variables}, "panels": panels,
            "annotations": {"list": []}}


VMS = 'instance=~"$instance"'
NET = 'device!~"lo|docker.*|veth.*|br-.*"'
DISK = 'device!~"loop.*|sr.*"'
FS = 'mountpoint="/",fstype!~"tmpfs|overlay"'
RI = "$__rate_interval"

# --- VM performance
vm = dashboard(
    "vm-performance", "VM Performance",
    "Host metrics from Node Exporter on every VM: CPU, memory, disk, disk I/O, network.",
    [
        row("Overview", 0),
        stat("VMs up", 'sum(up{job="node"})', "none", 0, 1,
             desc="Node Exporter targets answering right now (out of all VMs in the inventory)."),
        stat("VMs down", 'count(up{job="node"} == 0) or vector(0)', "none", 6, 1,
             desc="VMs Prometheus cannot reach. Anything above 0 is an outage.",
             thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}]),
        stat("Average CPU", f'100 * (1 - avg(rate(node_cpu_seconds_total{{mode="idle",{VMS}}}[5m])))', "percent", 12, 1,
             thresholds=steps(70, 80)),
        stat("Average memory used",
             f'100 * (1 - sum(node_memory_MemAvailable_bytes{{{VMS}}}) / sum(node_memory_MemTotal_bytes{{{VMS}}}))',
             "percent", 18, 1,
             thresholds=steps(80, 90)),
        row("CPU and memory", 5),
        ts("CPU usage per VM",
           [(f'100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{{mode="idle",{VMS}}}[{RI}])))',
             "{{instance}}")],
           "percent", 0, 6, desc="Share of CPU time not idle. Alert: above 80% for 5 minutes.", maxv=100),
        ts("Memory usage per VM",
           [(f'100 * (1 - node_memory_MemAvailable_bytes{{{VMS}}} / node_memory_MemTotal_bytes{{{VMS}}})',
             "{{instance}}")],
           "percent", 12, 6, desc="RAM in use (excluding cache that can be freed). Alert: above 90% for 5 minutes.",
           maxv=100),
        ts("Load average (1 min)", [(f'node_load1{{{VMS}}}', "{{instance}}")], "short", 0, 14,
           desc="Processes waiting for CPU. Above the number of cores = the VM is overloaded."),
        bargauge("Disk space used (/)",
                 f'100 * (1 - node_filesystem_avail_bytes{{{FS},{VMS}}} / node_filesystem_size_bytes{{{FS},{VMS}}})',
                 "percent", "{{instance}}", 12, 14,
                 desc="Root filesystem usage. Alert: less than 20% free (above 80% used)."),
        row("Disk I/O and network", 22),
        ts("Disk read",
           [(f'sum by (instance) (rate(node_disk_read_bytes_total{{{DISK},{VMS}}}[{RI}]))', "{{instance}}")],
           "Bps", 0, 23, desc="Bytes read from disk per second."),
        ts("Disk write",
           [(f'sum by (instance) (rate(node_disk_written_bytes_total{{{DISK},{VMS}}}[{RI}]))', "{{instance}}")],
           "Bps", 12, 23, desc="Bytes written to disk per second."),
        ts("Network received",
           [(f'sum by (instance) (rate(node_network_receive_bytes_total{{{NET},{VMS}}}[{RI}]))', "{{instance}}")],
           "Bps", 0, 31, desc="Incoming traffic on the VM's real network interfaces."),
        ts("Network sent",
           [(f'sum by (instance) (rate(node_network_transmit_bytes_total{{{NET},{VMS}}}[{RI}]))', "{{instance}}")],
           "Bps", 12, 31, desc="Outgoing traffic on the VM's real network interfaces."),
    ],
    [var("instance", "VM", 'label_values(up{job="node"}, instance)')],
    ["sherlock-logs", "vm", "node-exporter"],
)

# --- Docker containers
C = 'name!="",instance=~"$instance",name=~"$container"'
NOJVM = 'name!~"es0[0-9]|logstash"'  # Java services: always near their memory limit by design
docker = dashboard(
    "docker-containers", "Docker Containers",
    "Container metrics from cAdvisor on every Docker VM: health, CPU, memory, restarts.",
    [
        row("Health", 0),
        stat("Running containers", f'count(count by (instance, name) (container_last_seen{{{C}}}))', "none", 0, 1,
             desc="Containers cAdvisor currently sees."),
        stat("Restarts (last 15 min)",
             f'sum(resets(container_cpu_usage_seconds_total{{{C}}}[15m])) or vector(0)', "none", 6, 1,
             desc="Each restart starts a new CPU counter at 0; resets() counts those drops. "
                  "Alert: more than 3 for one container in 15 minutes.",
             thresholds=steps(1, 4)),
        stat("cAdvisor targets up", 'sum(up{job="cadvisor"})', "none", 12, 1,
             desc="Docker VMs whose container metrics Prometheus receives."),
        stat("Highest memory vs limit",
             f'max(container_memory_working_set_bytes{{{C},{NOJVM}}} '
             f'/ (container_spec_memory_limit_bytes{{{C},{NOJVM}}} > 0)) * 100 '
             f'or vector(0)', "percent", 18, 1,
             desc="The container closest to its memory limit (same containers as the alert). Alert: above 80%. "
                  "Only containers WITH a limit count; es01, es02 and logstash always sit near theirs (Java heap).",
             thresholds=steps(70, 80)),
        table("Container status",
              [f'time() - max by (instance, name, image) (container_start_time_seconds{{{C}}})',
               f'max by (instance, name, image) (resets(container_cpu_usage_seconds_total{{{C}}}[1h]))'],
              0, 5, h=8,
              desc="Age (seconds since the container was created) and restarts in the last hour, per container."),
        row("Resources", 13),
        ts("CPU per container",
           [(f'sum by (instance, name) (rate(container_cpu_usage_seconds_total{{{C}}}[{RI}])) * 100',
             "{{instance}} / {{name}}")],
           "percent", 0, 14, desc="100% = one full CPU core."),
        ts("Memory per container",
           [(f'sum by (instance, name) (container_memory_working_set_bytes{{{C}}})', "{{instance}} / {{name}}")],
           "bytes", 12, 14,
           desc="Working set = memory the container really uses (what the kernel's OOM limit checks)."),
        ts("Memory vs limit (containers with a limit)",
           [(f'container_memory_working_set_bytes{{{C}}} / (container_spec_memory_limit_bytes{{{C}}} > 0) * 100',
             "{{instance}} / {{name}}")],
           "percent", 0, 22, desc="Alert: above 80% of the container's own memory limit.", maxv=100),
        ts("Restarts (last 15 min, per container)",
           [(f'resets(container_cpu_usage_seconds_total{{{C}}}[15m])', "{{instance}} / {{name}}")],
           "none", 12, 22, desc="Alert: more than 3 restarts in 15 minutes."),
    ],
    [var("instance", "VM", 'label_values(up{job="cadvisor"}, instance)'),
     var("container", "Container", 'label_values(container_last_seen{name!=""}, name)')],
    ["sherlock-logs", "docker", "cadvisor"],
)

# --- Application performance
APP = 'job=~"backend|frontend"'
app = dashboard(
    "app-performance", "Application Performance",
    "The app's own metrics: request rate, error rate, response times, and the custom metrics.",
    [
        row("Overview", 0),
        stat("App targets up", f'sum(up{{{APP}}})', "none", 0, 1,
             desc="Backend + frontend instances Prometheus can scrape."),
        stat("Requests per second", f'sum(rate(http_requests_total{{{APP}}}[5m]))', "reqps", 6, 1),
        stat("Error rate (5xx)",
             f'100 * sum(rate(http_requests_total{{{APP},status="5xx"}}[5m])) '
             f'/ sum(rate(http_requests_total{{{APP}}}[5m])) or vector(0)', "percent", 12, 1,
             thresholds=steps(1, 5)),
        stat("Response time p95",
             f'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{APP}}}[5m])))',
             "s", 18, 1, desc="95% of requests were faster than this.",
             thresholds=steps(1, 2)),
        row("Traffic and errors", 5),
        ts("Requests per second by service",
           [(f'sum by (job) (rate(http_requests_total{{{APP}}}[{RI}]))', "{{job}}")], "reqps", 0, 6),
        ts("Error rate by service",
           [(f'100 * sum by (job) (rate(http_requests_total{{{APP},status="5xx"}}[{RI}])) '
             f'/ sum by (job) (rate(http_requests_total{{{APP}}}[{RI}]))', "{{job}} 5xx"),
            (f'100 * sum by (job) (rate(http_requests_total{{{APP},status="4xx"}}[{RI}])) '
             f'/ sum by (job) (rate(http_requests_total{{{APP}}}[{RI}]))', "{{job}} 4xx")],
           "percent", 12, 6, desc="Share of requests that failed. 5xx = server error, 4xx = bad request."),
        row("Response times", 14),
        ts("Response time percentiles",
           [(f'histogram_quantile(0.50, sum by (le, job) (rate(http_request_duration_seconds_bucket{{{APP}}}[{RI}])))',
             "{{job}} p50"),
            (f'histogram_quantile(0.95, sum by (le, job) (rate(http_request_duration_seconds_bucket{{{APP}}}[{RI}])))',
             "{{job}} p95"),
            (f'histogram_quantile(0.99, sum by (le, job) (rate(http_request_duration_seconds_bucket{{{APP}}}[{RI}])))',
             "{{job}} p99")],
           "s", 0, 15, desc="p95 = 95% of requests were faster than this line."),
        ts("Average response time by endpoint",
           [(f'sum by (job, handler) (rate(http_request_duration_seconds_sum{{{APP}}}[{RI}])) '
             f'/ sum by (job, handler) (rate(http_request_duration_seconds_count{{{APP}}}[{RI}]))',
             "{{job}} {{handler}}")],
           "s", 12, 15),
        row("Custom application metrics", 23),
        ts("Backend: time to collect system facts (metrics_collect_seconds)",
           [('histogram_quantile(0.95, sum by (le) (rate(metrics_collect_seconds_bucket[$__rate_interval])))', "p95"),
            ('sum(rate(metrics_collect_seconds_sum[$__rate_interval])) '
             '/ sum(rate(metrics_collect_seconds_count[$__rate_interval]))', "average")],
           "s", 0, 24, desc="Custom histogram in the backend. Most of it is the 1-second CPU measurement."),
        ts("Frontend: failed backend calls (frontend_backend_errors_total)",
           [('sum by (instance, reason) (increase(frontend_backend_errors_total[5m]))', "{{instance}} {{reason}}")],
           "none", 12, 24,
           desc="Custom counter in the frontend: backend calls that failed in the last 5 minutes, by reason."),
    ],
    [],
    ["sherlock-logs", "application"],
)

# =====================================================================================
# KIBANA (Elasticsearch log indices)
# =====================================================================================
objs = []
IDX_REF = "kibanaSavedObjectMeta.searchSourceJSON.index"


def source(query=""):
    return J({"query": {"query": query, "language": "kuery"}, "filter": [], "indexRefName": IDX_REF})


def data_view(id_, title, name):
    objs.append({"type": "index-pattern", "id": id_,
                 "attributes": {"title": title, "name": name, "timeFieldName": "@timestamp"}, "references": []})


def search(id_, title, view, columns, query=""):
    objs.append({"type": "search", "id": id_,
                 "attributes": {"title": title, "description": "", "columns": columns,
                                "sort": [["@timestamp", "desc"]],
                                "kibanaSavedObjectMeta": {"searchSourceJSON": source(query)}},
                 "references": [{"name": IDX_REF, "type": "index-pattern", "id": view}]})


def count_agg():
    return {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}}


def terms(id_, field, schema, size=10):
    return {"id": id_, "enabled": True, "type": "terms", "schema": schema,
            "params": {"field": field, "size": size, "order": "desc", "orderBy": "1",
                       "otherBucket": True, "otherBucketLabel": "Other", "missingBucket": False}}


def vis(id_, title, view, vis_type, params, aggs, query="", desc=""):
    vis_state = {"title": title, "type": vis_type, "params": params, "aggs": aggs}
    objs.append({"type": "visualization", "id": id_,
                 "attributes": {"title": title, "description": desc, "visState": J(vis_state),
                                "uiStateJSON": "{}", "version": 1,
                                "kibanaSavedObjectMeta": {"searchSourceJSON": source(query)}},
                 "references": [{"name": IDX_REF, "type": "index-pattern", "id": view}]})


def over_time(id_, title, view, split_field, query="", desc=""):
    params = {
        "type": "histogram", "addTooltip": True, "addLegend": True, "legendPosition": "right",
        "times": [], "addTimeMarker": False,
        "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom", "show": True,
                          "style": {}, "scale": {"type": "linear"},
                          "labels": {"show": True, "filter": True, "truncate": 100}, "title": {}}],
        "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value", "position": "left",
                       "show": True, "style": {}, "scale": {"type": "linear", "mode": "normal"},
                       "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                       "title": {"text": "Log lines"}}],
        "seriesParams": [{"show": True, "type": "histogram", "mode": "stacked",
                          "data": {"label": "Log lines", "id": "1"}, "valueAxis": "ValueAxis-1",
                          "drawLinesBetweenPoints": True, "lineWidth": 2, "showCircles": True}],
        "grid": {"categoryLines": False}, "labels": {"show": False},
        "thresholdLine": {"show": False, "value": 10, "width": 1, "style": "full", "color": "#E7664C"},
    }
    aggs = [count_agg(),
            {"id": "2", "enabled": True, "type": "date_histogram", "schema": "segment",
             "params": {"field": "@timestamp", "interval": "auto", "min_doc_count": 1, "extended_bounds": {}}},
            terms("3", split_field, "group")]
    vis(id_, title, view, "histogram", params, aggs, query, desc)


def pie(id_, title, view, field, query="", desc=""):
    params = {"type": "pie", "addTooltip": True, "legendDisplay": "show", "legendPosition": "right",
              "isDonut": True, "labels": {"show": True, "values": True, "last_level": True, "truncate": 100}}
    vis(id_, title, view, "pie", params, [count_agg(), terms("2", field, "segment")], query, desc)


def kibana_table(id_, title, view, fields, query="", extra_metrics=(), desc=""):
    params = {"perPage": 10, "showPartialRows": False, "showMetricsAtAllLevels": False,
              "showTotal": False, "totalFunc": "sum", "percentageCol": ""}
    aggs = [count_agg()] + list(extra_metrics)
    for i, f in enumerate(fields):
        aggs.append(terms(str(10 + i), f, "bucket", size=20))
    vis(id_, title, view, "table", params, aggs, query, desc)


def kibana_dashboard(id_, title, desc, panels):
    """panels: list of (type, id, x, y, w, h)"""
    pj, refs = [], []
    for i, (ptype, pid, x, y, w, h) in enumerate(panels, 1):
        pj.append({"type": ptype, "panelIndex": str(i), "panelRefName": f"panel_{i}",
                   "gridData": {"x": x, "y": y, "w": w, "h": h, "i": str(i)},
                   "embeddableConfig": {"enhancements": {}}})
        refs.append({"name": f"{i}:panel_{i}", "type": ptype, "id": pid})
    objs.append({"type": "dashboard", "id": id_,
                 "attributes": {"title": title, "description": desc, "panelsJSON": J(pj),
                                "optionsJSON": J({"useMargins": True, "syncColors": False,
                                                  "hidePanelTitles": False}),
                                "timeRestore": True, "timeFrom": "now-1h", "timeTo": "now",
                                "refreshInterval": {"pause": False, "value": 30000},
                                "kibanaSavedObjectMeta": {"searchSourceJSON": J(
                                    {"query": {"query": "", "language": "kuery"}, "filter": []})}},
                 "references": refs})


# --- Data views ---------------------------------------------------------------------
data_view("system-logs", "system-logs-*", "System logs")
data_view("app-logs", "app-logs-*", "Application logs")
# All container output: the app containers' lines live in app-logs, so both are included.
data_view("docker-logs", "docker-logs-*,app-logs-*", "Docker logs")

# --- System logs -----------------------------------------------------------------------
over_time("sys-volume", "System logs over time, per VM", "system-logs", "agent.name",
          desc="Log lines per VM. A sudden spike usually means something is wrong on that VM.")
kibana_table("sys-programs", "Top programs writing system logs", "system-logs", ["system.program"])
kibana_table("sys-failed-logins", "Failed SSH logins per VM", "system-logs", ["agent.name"],
             query='log_type:"auth" and system.message:("Failed password" or "Invalid user")',
             desc="Someone tried an unknown user or a wrong password. "
                  "Password login is off, so most attempts show up as 'Invalid user'.")
search("sys-search", "System logs - all VMs", "system-logs",
       ["agent.name", "log_type", "system.program", "system.message"])
kibana_dashboard("sherlock-system-logs", "System Logs",
                 "syslog, kernel log (dmesg) and auth.log from every VM.",
                 [("visualization", "sys-volume", 0, 0, 48, 12),
                  ("visualization", "sys-programs", 0, 12, 24, 14),
                  ("visualization", "sys-failed-logins", 24, 12, 24, 14),
                  ("search", "sys-search", 0, 26, 48, 20)])

# --- Application logs -------------------------------------------------------------------
over_time("app-volume", "Application log lines over time, per service", "app-logs", "app.service",
          desc="backend, frontend and nginx (load balancer).")
pie("app-status", "HTTP status codes (app requests)", "app-logs", "app.status", query='message:"request"',
    desc="200 = OK, 503 = the frontend could not reach the backend.")
pie("app-levels", "Log levels", "app-logs", "log.level", query="log.level:*")
kibana_table("app-endpoints", "Requests per endpoint, with average response time", "app-logs",
             ["app.service", "app.path"], query='message:"request"',
             extra_metrics=[{"id": "2", "enabled": True, "type": "avg", "schema": "metric",
                             "params": {"field": "app.duration_ms", "customLabel": "Average ms"}}])
search("app-errors", "Application errors", "app-logs",
       ["app.service", "log.level", "message", "app.reason", "app.path", "app.status"],
       query='log.level:"ERROR" or app.status >= 500')
search("app-search", "Application logs - all", "app-logs",
       ["app.service", "agent.name", "app.method", "app.path", "app.status", "app.duration_ms", "message"])
kibana_dashboard("sherlock-app-logs", "Application Logs",
                 "The app's JSON logs (backend, frontend) and nginx access/error logs from the load balancer.",
                 [("visualization", "app-volume", 0, 0, 48, 12),
                  ("visualization", "app-status", 0, 12, 16, 14),
                  ("visualization", "app-levels", 16, 12, 16, 14),
                  ("visualization", "app-endpoints", 32, 12, 16, 14),
                  ("search", "app-errors", 0, 26, 48, 14),
                  ("search", "app-search", 0, 40, 48, 20)])

# --- Docker logs ---------------------------------------------------------------------------
D = 'log_type:"docker"'
over_time("docker-volume", "Container log lines over time, per container", "docker-logs", "container.name",
          query=D)
pie("docker-streams", "stdout vs stderr", "docker-logs", "stream", query=D,
    desc="stderr is where most programs write warnings and errors.")
kibana_table("docker-per-vm", "Log lines per VM and container", "docker-logs",
             ["agent.name", "container.name"], query=D)
search("docker-stderr", "Container errors (stderr)", "docker-logs",
       ["agent.name", "container.name", "message"], query='log_type:"docker" and stream:"stderr"')
search("docker-search", "Container logs - all", "docker-logs",
       ["agent.name", "container.name", "stream", "message"], query=D)
kibana_dashboard("sherlock-docker-logs", "Docker Logs",
                 "stdout and stderr of every container on every Docker VM.",
                 [("visualization", "docker-volume", 0, 0, 48, 12),
                  ("visualization", "docker-streams", 0, 12, 16, 14),
                  ("visualization", "docker-per-vm", 16, 12, 32, 14),
                  ("search", "docker-stderr", 0, 26, 48, 14),
                  ("search", "docker-search", 0, 40, 48, 20)])


# =====================================================================================
# Write the files
# =====================================================================================
def main():
    grafana_dir = os.path.join(FILES, "grafana-dashboards")
    kibana_dir = os.path.join(FILES, "kibana")
    os.makedirs(grafana_dir, exist_ok=True)
    os.makedirs(kibana_dir, exist_ok=True)

    for name, d in [("vm-performance", vm), ("docker-containers", docker), ("app-performance", app)]:
        with open(os.path.join(grafana_dir, f"{name}.json"), "w") as f:
            f.write(pretty(d) + "\n")

    with open(os.path.join(kibana_dir, "dashboards.ndjson"), "w") as f:
        for o in objs:
            f.write(json.dumps(o, separators=(",", ":")) + "\n")

    print("Grafana: 3 dashboards ->", os.path.relpath(grafana_dir, ROOT))
    print(f"Kibana:  {len(objs)} saved objects (3 data views, 5 searches, 10 visualizations, 3 dashboards) ->",
          os.path.relpath(kibana_dir, ROOT))


if __name__ == "__main__":
    main()
