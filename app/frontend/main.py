"""
main.py — FastAPI web layer for the frontend.
Calls the backend's /metrics endpoint and renders the result as HTML.
"""
import os
import socket

import httpx
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Serve style.css (and any future static assets) at /static/...
app.mount("/static", StaticFiles(directory="static"), name="static")

# Read the backend URL from an environment variable, with a fallback
# default for local testing.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://192.168.56.13:3000")

# Baked into the image at build time (Dockerfile ARG).
APP_VERSION = os.environ.get("APP_VERSION", "dev")


@app.get("/health")
def health():
    """Cheap 'am I alive?' check used by Ansible after each deploy."""
    return {"status": "ok", "version": APP_VERSION}


@app.api_route("/", methods=["GET", "HEAD"])
def home(request: Request):
    """Fetch metrics from the backend and render them on a webpage."""
    try:
        # timeout: never hang forever if the backend is down
        response = httpx.get(f"{BACKEND_URL}/metrics", timeout=5)
        response.raise_for_status()
        backend_data, error = response.json(), None
    except httpx.HTTPError as exc:
        backend_data, error = None, f"Backend unreachable ({exc.__class__.__name__})"

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
