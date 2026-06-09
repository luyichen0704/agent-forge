"""Real LLM-driven exploration of a data source.

Runs as a background task: streams phase/extraction events into
`exploration_events` (consumed by the Live screen over SSE), uses the P-LLM
model to extract candidate operations from the source, persists them as
`discovered_operations`, and registers any new ones into the Operation Registry
as `pending` (write ops await human review; reads can auto-activate).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models.registry import Operation, OperationPermission
from app.models.sources import (
    DataSource, DiscoveredOperation, ExplorationEvent, ExplorationJob,
)
from app.services.llm import llm

EXTRACT_SYSTEM = """\
You explore an enterprise data source and propose callable operations an AI agent
could expose. Return JSON:
{"entities":[{"name":..,"fields":[..]}],
 "operations":[{"key":"area.verb","kind":"query|mutation","desc":".."}],
 "rules":[".."], "chains":[".."]}
Keep it realistic and concise (3-6 operations)."""


async def _emit(db, job_id: uuid.UUID, event_type: str, payload: dict) -> None:
    seq = (
        await db.execute(
            select(func.coalesce(func.max(ExplorationEvent.seq), 0)).where(
                ExplorationEvent.job_id == job_id
            )
        )
    ).scalar_one() + 1
    db.add(ExplorationEvent(job_id=job_id, seq=seq, event_type=event_type,
                            payload_json=payload, created_at=datetime.now(timezone.utc)))
    await db.flush()


async def run_exploration(job_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        job = await db.get(ExplorationJob, job_id)
        if job is None:
            return
        source = await db.get(DataSource, job.source_id)
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)

        phases = [(1, "全局认知"), (2, "深度探索"), (3, "操作生成"), (4, "能力标注")]
        for ph, label in phases[:2]:
            job.phase = ph
            job.progress = ph * 20
            await _emit(db, job_id, "phase", {"phase": ph, "label": label})
            await db.commit()
            await asyncio.sleep(0.4)

        # ---- real extraction via LLM (any failure must not leave job 'running') ----
        try:
            data, _ = await llm.structured(
                settings.pllm_model, EXTRACT_SYSTEM,
                f"Source type: {source.type}\nConnector: {source.connector_kind}\n"
                f"Connection: {source.conn}\nName: {source.name}",
                max_tokens=900,
            )
        except Exception as exc:  # noqa: BLE001 — surface any error to the job
            await _emit(db, job_id, "error", {"error": f"{type(exc).__name__}: {exc}"})
            job.status = "error"
            source.status = "error"
            await db.commit()
            return

        job.phase = 3
        job.progress = 70
        for op in data.get("operations", [])[:6]:
            key = str(op.get("key", "")).strip()
            kind = op.get("kind") if op.get("kind") in ("query", "mutation") else "query"
            if not key:
                continue
            db.add(DiscoveredOperation(job_id=job_id, key=key, kind=kind,
                                       input_schema={}, output_schema={},
                                       capability_requirements={}, executor_hint="FunctionExecutor"))
            await _emit(db, job_id, "op", {"key": key, "kind": kind, "desc": op.get("desc", "")})
            await _register_operation(db, source.tenant_id, key, kind, job_id)
            await db.commit()
            await asyncio.sleep(0.25)

        for rule in data.get("rules", [])[:4]:
            await _emit(db, job_id, "rule", {"text": rule})
        await db.commit()

        job.phase = 4
        job.progress = 100
        job.status = "done"
        job.finished_at = datetime.now(timezone.utc)
        source.status = "connected"
        await _emit(db, job_id, "done", {"operations": len(data.get("operations", []))})
        await db.commit()


async def _register_operation(db, tenant_id, key, kind, job_id) -> None:
    existing = (
        await db.execute(
            select(Operation).where(Operation.tenant_id == tenant_id, Operation.op_key == key)
        )
    ).scalar_one_or_none()
    if existing:
        return
    confirm = "confirm" if kind == "mutation" else "auto"
    status = "pending" if kind == "mutation" else "active"
    op = Operation(tenant_id=tenant_id, op_key=key, version=1, kind=kind, confirm_level=confirm,
                   risk_level="high" if kind == "mutation" else "low", status=status,
                   executor_binding="FunctionExecutor", rollback_binding="FunctionExecutor",
                   policy_ref=f"{key.replace('.', '_')}_policy", created_from_job_id=job_id,
                   published_at=datetime.now(timezone.utc) if status == "active" else None)
    db.add(op)
    await db.flush()
    # default grants: employees + admins; reads also to customers (scoped self)
    grants = [("employee", None), ("admin", None)]
    if kind == "query":
        grants.append(("customer", "self"))
    for role, scope in grants:
        db.add(OperationPermission(operation_id=op.id, subject_type="role", subject_id=role,
                                   effect="allow", condition_json={"scope": scope} if scope else {}))
