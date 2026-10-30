"""Unit tests for metrics.py - the functions that collect system facts."""
from types import SimpleNamespace

import metrics


def test_memory_is_converted_from_bytes_to_mb(monkeypatch):
    fake = SimpleNamespace(total=2 * 1024 * 1024 * 1024, used=512 * 1024 * 1024, percent=25.0)
    monkeypatch.setattr(metrics.psutil, "virtual_memory", lambda: fake)

    assert metrics.get_memory_info() == {"total_mb": 2048.0, "used_mb": 512.0, "percent_used": 25.0}


def test_cpu_info_has_cores_and_usage(monkeypatch):
    monkeypatch.setattr(metrics.psutil, "cpu_count", lambda logical: 4)
    monkeypatch.setattr(metrics.psutil, "cpu_percent", lambda interval: 12.5)

    assert metrics.get_cpu_info() == {"cores_count": 4, "usage_percent": 12.5}


def test_collect_all_returns_every_section(monkeypatch):
    # Skip the real 1-second CPU measurement to keep the test fast.
    monkeypatch.setattr(metrics.psutil, "cpu_percent", lambda interval: 0.0)

    data = metrics.collect_all()

    assert set(data) == {"hostname", "os", "cpu", "memory"}
    assert data["hostname"]
    assert data["memory"]["total_mb"] > 0
