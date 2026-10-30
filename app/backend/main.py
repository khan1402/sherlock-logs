"""
main.py — FastAPI web layer for the backend.
Knows nothing about HOW metrics are gathered — just imports
collect_all() and serves it over HTTP.
"""
import os

from fastapi import FastAPI

import metrics

# Baked into the image at build time (Dockerfile ARG). Lets us SEE which
# version is live after every deploy - the proof the CI/CD pipeline worked.
APP_VERSION = os.environ.get("APP_VERSION", "dev")

app = FastAPI()


@app.get("/metrics")
def read_metrics():
    """Return all system facts as JSON, plus the running version."""
    data = metrics.collect_all()
    data["version"] = APP_VERSION
    return data


@app.get("/health")
def health():
    """Cheap 'am I alive?' check used by Ansible after each deploy."""
    return {"status": "ok", "version": APP_VERSION}
