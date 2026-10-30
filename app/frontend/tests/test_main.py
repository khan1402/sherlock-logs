"""Unit tests for the frontend (main.py). The backend is faked, so these
tests check the frontend's own behaviour: rendering, versions, errors."""
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


def test_health_says_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_page_shows_backend_metrics_and_both_versions(monkeypatch):
    monkeypatch.setattr(main.httpx, "get", lambda url, timeout: FakeResponse())
    monkeypatch.setattr(main, "APP_VERSION", "abc1234")

    response = client.get("/")

    assert response.status_code == 200
    assert "app-server" in response.text
    assert "Frontend abc1234" in response.text
    assert "Backend abc1234" in response.text


def test_page_returns_503_when_backend_is_down(monkeypatch):
    def backend_down(url, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(main.httpx, "get", backend_down)

    response = client.get("/")

    assert response.status_code == 503
    assert "Backend unreachable" in response.text
    assert "Backend unavailable" in response.text
