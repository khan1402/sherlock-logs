"""
logging_setup.py — make every log line ONE JSON object.

Why JSON: Filebeat ships the container's stdout to Logstash, and Logstash
can read a JSON line field by field (level, path, status, ...) without
fragile regex parsing. Kibana can then filter on those fields directly.

"""
import logging
import socket
import sys

from pythonjsonlogger.json import JsonFormatter


class _DropColorMessage(logging.Filter):
    """uvicorn adds a 'color_message' copy with terminal colour codes - not useful in JSON."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.pop("color_message", None)
        return True


def setup_logging(service: str, version: str) -> logging.Logger:
    """Send all logs (ours + uvicorn's) to stdout as JSON. Returns the app logger."""
    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "time", "levelname": "level", "name": "logger"},
        # Added to EVERY line, so Kibana can tell services and VMs apart.
        static_fields={"service": service, "version": version, "host": socket.gethostname()},
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(_DropColorMessage())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # uvicorn sets up its own plain-text handlers before it imports the app.
    # Remove them so uvicorn's messages (startup, errors) flow up to the JSON handler.
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True

    # uvicorn's access log is switched off: our own request log in main.py
    # replaces it, with separate fields (method, path, status, duration_ms).
    logging.getLogger("uvicorn.access").disabled = True

    # httpx logs every outgoing call at INFO - too noisy, keep only warnings.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logging.getLogger("app")
