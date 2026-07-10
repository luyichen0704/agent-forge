"""Arq worker — runs durable background jobs.

Start it as a separate process:
    uv run arq app.worker.WorkerSettings
"""
from __future__ import annotations

import logging
import uuid

from app.logging_config import configure_logging
from app.queue import redis_settings
from app.services.explorer import run_exploration

configure_logging()
log = logging.getLogger("agentforge.worker")


async def explore_task(ctx: dict, job_id: str) -> str:
    log.info("explore_task start job=%s", job_id)
    await run_exploration(uuid.UUID(job_id))
    log.info("explore_task done job=%s", job_id)
    return job_id


class WorkerSettings:
    functions = [explore_task]
    redis_settings = redis_settings()
    max_jobs = 10
    # comprehensive discovery names hundreds of endpoints in many LLM batches
    job_timeout = 3600
    keep_result = 3600
