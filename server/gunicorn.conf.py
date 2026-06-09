"""Gunicorn config for the agent-forge API (uvicorn workers).

Run:  uv run gunicorn -c gunicorn.conf.py app.main:app
Logs go to stdout/stderr (captured by systemd-journald / Docker). For file logs
set LOG_DIR in the environment (app writes <LOG_DIR>/app.log itself); access/error
below can additionally be redirected to files via GUNICORN_*_LOG.
"""
import multiprocessing
import os

# bind to loopback only — nginx terminates TLS and proxies to us
bind = os.getenv("API_BIND", "127.0.0.1:8099")

# 2*CPU+1 is the usual starting point; override with WEB_CONCURRENCY
workers = int(os.getenv("WEB_CONCURRENCY", str(multiprocessing.cpu_count() * 2 + 1)))
worker_class = "uvicorn.workers.UvicornWorker"

timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))      # LLM calls can be slow
graceful_timeout = 30
keepalive = 15
max_requests = 1000
max_requests_jitter = 100

# "-" = stdout/stderr; set to a path for file logging
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("LOG_LEVEL", "info").lower()
proc_name = "agent-forge-api"
