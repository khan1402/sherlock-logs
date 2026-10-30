"""Unit tests for the backend API (main.py)."""
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_health_says_ok_and_shows_version(monkeypatch):
    monkeypatch.setattr(main, "APP_VERSION", "abc1234")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "abc1234"}


def test_metrics_endpoint_adds_the_version(monkeypatch):
    monkeypatch.setattr(main.metrics, "collect_all", lambda: {"hostname": "app-server"})
    monkeypatch.setattr(main, "APP_VERSION", "abc1234")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.json() == {"hostname": "app-server", "version": "abc1234"}
