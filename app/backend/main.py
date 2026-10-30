"""
main.py — FastAPI web layer for the backend.
Knows nothing about HOW system facts are gathered — just imports
collect_all() and serves it over HTTP.

Endpoints:
  /api/metrics  system facts as JSON (read by the frontend)
  /health       "am I alive?" (used by Ansible and the CI pipeline)
  /metrics      Prometheus metrics in text format (scraped by Prometheus)
"""
import os
import time

from fastapi import FastAPI, Request
from prometheus_client import Histogram
from prometheus_fastapi_instrumentator import Instrumentator

import metrics
from logging_setup import setup_logging

# Baked into the image at build time (Dockerfile ARG). Lets us SEE which
# version is live after every deploy - the proof the CI/CD pipeline worked.
APP_VERSION = os.environ.get("APP_VERSION", "dev")

log = setup_logging(service="backend", version=APP_VERSION)

app = FastAPI()

# --- Prometheus metrics -------------------------------------------------------
# Standard HTTP metrics for every endpoint, added automatically:
#   http_requests_total{handler, method, status}   -> request + error rates
#   http_request_duration_seconds{handler, method} -> response times
# /metrics and /health are left out so scrapes and health checks don't
# distort the numbers of real traffic. The patterns are regular expressions:
# ^ and $ make them exact, otherwise "/metrics" would also match "/api/metrics".
Instrumentator(excluded_handlers=["^/metrics$", "^/health$"]).instrument(app).expose(app, include_in_schema=False)

# Custom application metric: how long collecting the system facts takes.
# A histogram counts the calls AND sorts them into time buckets, so Grafana
# can show both "calls per second" and "95% of calls were faster than X".
METRICS_COLLECT_SECONDS = Histogram(
    "metrics_collect_seconds",
    "Time spent collecting system facts (CPU, memory, OS) for /api/metrics",
    buckets=(0.1, 0.5, 1.0, 1.5, 2.0, 5.0),
)


# --- Request log --------------------------------------------------------------
# One JSON line per request. Replaces uvicorn's plain-text access log, which
# logging_setup.py switches off.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    if request.url.path not in ("/metrics", "/health"):  # skip scrape/health noise
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                "client": request.client.host if request.client else None,
            },
        )
    return response


# --- Endpoints ------------------------------------------------------------------
@app.get("/api/metrics")
def read_metrics():
    """Return all system facts as JSON, plus the running version."""
    with METRICS_COLLECT_SECONDS.time():
        data = metrics.collect_all()
    data["version"] = APP_VERSION
    return data


@app.get("/health")
def health():
    """Cheap 'am I alive?' check used by Ansible after each deploy."""
    return {"status": "ok", "version": APP_VERSION}
