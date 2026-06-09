"""Centralised logging setup.

Logs always go to stdout (captured by systemd-journald or Docker). When
`LOG_DIR` is set, a rotating file handler is added at `<LOG_DIR>/app.log`.
Set `LOG_JSON=true` for structured one-line-JSON logs in production.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
from pathlib import Path

from app.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status", "latency_ms", "actor"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_TEXT = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter: logging.Formatter = JsonFormatter() if settings.log_json else logging.Formatter(_TEXT)

    handlers: list[logging.Handler] = []
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    handlers.append(stream)

    if settings.log_dir:
        Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
        fileh = logging.handlers.RotatingFileHandler(
            os.path.join(settings.log_dir, "app.log"),
            maxBytes=20 * 1024 * 1024, backupCount=10, encoding="utf-8",
        )
        fileh.setFormatter(formatter)
        handlers.append(fileh)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = handlers

    # align uvicorn/gunicorn loggers with our handlers/format
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error", "gunicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = handlers
        lg.setLevel(level)
        lg.propagate = False


log = logging.getLogger("agentforge")
