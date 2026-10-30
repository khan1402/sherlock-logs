"""Unit tests for the frontend (main.py). The backend is faked, so these
tests check the frontend's own behaviour: rendering, versions, errors, metrics."""
import json
import logging

import httpx
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

FAKE_METRICS = {
    "hostname": "app-server",
    "os": "Linux 5.15.0",
    "cpu": {"cores_count": 1, "usage_percent": 3.5},
    "memory": {"total_mb": 957.4, "used_mb": 250.0, "percent_used": 26.1},
    "version": "abc1234",
}


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return FAKE_METRICS


def backend_down(url, timeout):
    raise httpx.ConnectError("connection refused")


def test_health_says_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_page_calls_the_backend_json_api(monkeypatch):
    called = {}

    def fake_get(url, timeout):
        called["url"] = url
        return FakeResponse()

    monkeypatch.setattr(main.httpx, "get", fake_get)

    client.get("/")

    assert called["url"].endswith("/api/metrics")


def test_page_shows_backend_metrics_and_both_versions(monkeypatch):
    monkeypatch.setattr(main.httpx, "get", lambda url, timeout: FakeResponse())
    monkeypatch.setattr(main, "APP_VERSION", "abc1234")

    response = client.get("/")

    assert response.status_code == 200
    assert "app-server" in response.text
    assert "Frontend abc1234" in response.text
    assert "Backend abc1234" in response.text


def test_page_returns_503_when_backend_is_down(monkeypatch):
    monkeypatch.setattr(main.httpx, "get", backend_down)

    response = client.get("/")

    assert response.status_code == 503
    assert "Backend unreachable" in response.text
    assert "Backend unavailable" in response.text


def test_backend_failure_increases_the_custom_counter(monkeypatch):
    monkeypatch.setattr(main.httpx, "get", backend_down)
    counter = main.BACKEND_ERRORS.labels(reason="ConnectError")
    before = counter._value.get()

    client.get("/")

    assert counter._value.get() == before + 1


def test_prometheus_endpoint_has_http_and_custom_metrics(monkeypatch):
    monkeypatch.setattr(main.httpx, "get", backend_down)
    client.get("/")  # one failing page, so both counters have data

    response = client.get("/metrics")

    assert response.status_code == 200
    assert 'frontend_backend_errors_total{reason="ConnectError"}' in response.text  # custom metric
    assert 'http_requests_total{handler="/",method="GET",status="5xx"}' in response.text  # error rate


def test_requests_are_logged_as_json(monkeypatch, caplog):
    monkeypatch.setattr(main.httpx, "get", lambda url, timeout: FakeResponse())

    with caplog.at_level(logging.INFO, logger="app"):
        client.get("/")

    records = [r for r in caplog.records if r.getMessage() == "request"]
    assert records, "no request log line found"

    # Format the record exactly like the real stdout handler does.
    json_handler = logging.getLogger().handlers[0]
    entry = json.loads(json_handler.format(records[-1]))
    assert entry["service"] == "frontend"
    assert entry["path"] == "/"
    assert entry["status"] == 200
