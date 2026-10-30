"""
main.py — FastAPI web layer for the frontend.
Calls the backend's /api/metrics endpoint and renders the result as HTML.

Endpoints:
  /         the web page (what users see through the load balancer)
  /health   "am I alive?" (used by Ansible and the CI pipeline)
  /metrics  Prometheus metrics in text format (scraped by Prometheus)
"""
import os
import socket
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

from logging_setup import setup_logging

# Read the backend URL from an environment variable, with a fallback
# default for local testing.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://192.168.56.13:3000")

# Baked into the image at build time (Dockerfile ARG).
APP_VERSION = os.environ.get("APP_VERSION", "dev")

log = setup_logging(service="frontend", version=APP_VERSION)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Serve style.css (and any future static assets) at /static/...
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Prometheus metrics -------------------------------------------------------
# Standard HTTP metrics, added automatically. On the frontend they show what
# USERS experience: page response time and how many pages failed (503).
# Patterns are regular expressions; ^ and $ make them exact matches.
Instrumentator(excluded_handlers=["^/metrics$", "^/health$"]).instrument(app).expose(app, include_in_schema=False)

# Custom application metric: failed calls to the backend, by reason
# (e.g. ConnectError = backend down, ReadTimeout = backend too slow).
BACKEND_ERRORS = Counter(
    "frontend_backend_errors_total",
    "Calls from the frontend to the backend API that failed",
    ["reason"],
)


# --- Request log --------------------------------------------------------------
# One JSON line per request. Replaces uvicorn's plain-text access log, which
# logging_setup.py switches off.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    path = request.url.path
    if path not in ("/metrics", "/health") and not path.startswith("/static"):
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                "client": request.client.host if request.client else None,
            },
        )
    return response


# --- Endpoints ------------------------------------------------------------------
@app.get("/health")
def health():
    """Cheap 'am I alive?' check used by Ansible after each deploy."""
    return {"status": "ok", "version": APP_VERSION}


@app.api_route("/", methods=["GET", "HEAD"])
def home(request: Request):
    """Fetch metrics from the backend and render them on a webpage."""
    try:
        # timeout: never hang forever if the backend is down
        response = httpx.get(f"{BACKEND_URL}/api/metrics", timeout=5)
        response.raise_for_status()
        backend_data, error = response.json(), None
    except httpx.HTTPError as exc:
        reason = exc.__class__.__name__
        BACKEND_ERRORS.labels(reason=reason).inc()
        log.error("backend call failed", extra={"reason": reason, "backend_url": BACKEND_URL})
        backend_data, error = None, f"Backend unreachable ({reason})"

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "web_server_hostname": socket.gethostname(),
            "data": backend_data,
            "error": error,
            "frontend_version": APP_VERSION,
        },
        status_code=200 if backend_data else 503,
    )
