"""Unit tests for the backend API (main.py)."""
import json
import logging

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_health_says_ok_and_shows_version(monkeypatch):
    monkeypatch.setattr(main, "APP_VERSION", "abc1234")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "abc1234"}


def test_api_metrics_endpoint_adds_the_version(monkeypatch):
    monkeypatch.setattr(main.metrics, "collect_all", lambda: {"hostname": "app-server"})
    monkeypatch.setattr(main, "APP_VERSION", "abc1234")

    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.json() == {"hostname": "app-server", "version": "abc1234"}


def test_prometheus_endpoint_has_http_and_custom_metrics(monkeypatch):
    monkeypatch.setattr(main.metrics, "collect_all", lambda: {"hostname": "app-server"})
    client.get("/api/metrics")  # one real request, so the counters have data

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "metrics_collect_seconds_count" in response.text  # custom metric
    assert 'http_requests_total{handler="/api/metrics"' in response.text  # standard HTTP metric


def test_requests_are_logged_as_json(monkeypatch, caplog):
    monkeypatch.setattr(main.metrics, "collect_all", lambda: {"hostname": "app-server"})

    with caplog.at_level(logging.INFO, logger="app"):
        client.get("/api/metrics")

    records = [r for r in caplog.records if r.getMessage() == "request"]
    assert records, "no request log line found"

    # Format the record exactly like the real stdout handler does.
    json_handler = logging.getLogger().handlers[0]
    entry = json.loads(json_handler.format(records[-1]))
    assert entry["service"] == "backend"
    assert entry["path"] == "/api/metrics"
    assert entry["status"] == 200
    assert entry["level"] == "INFO"


def test_uvicorn_logs_go_to_json_and_access_log_is_off():
    assert logging.getLogger("uvicorn.error").handlers == []
    assert logging.getLogger("uvicorn.error").propagate is True
    assert logging.getLogger("uvicorn.access").disabled is True
