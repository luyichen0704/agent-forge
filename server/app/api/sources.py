"""Data sources + exploration jobs (SSE live stream)."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.db import SessionLocal, get_db
from app.deps import Principal, get_principal, get_principal_qs
from app.models.registry import Operation
from app.models.sources import (
    DataSource, DiscoveredChain, DiscoveredEntity, DiscoveredOperation,
    DiscoveredRule, ExplorationEvent, ExplorationJob,
)
from app.queue import get_pool

router = APIRouter(tags=["sources"])


class SourceIn(BaseModel):
    type: str = Field(pattern="^(code|db|api|admin|doc)$")
    name: str = Field(min_length=1, max_length=120)
    connector_kind: str = Field(min_length=1, max_length=60)
    conn: str = Field(min_length=1, max_length=240)
    config_json: dict = Field(default_factory=dict)
    secret_ref: str | None = None


@router.get("/sources")
async def list_sources(p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (
        await db.execute(select(DataSource).where(DataSource.tenant_id == p.tenant_id).order_by(DataSource.created_at))
    ).scalars().all()
    def conn(s: DataSource) -> str:
        # connection strings can carry hosts/paths — full value is admin-only
        return s.conn if p.is_admin else (s.conn.split("·")[0].strip() if "·" in s.conn else "（已隐藏）")
    return {"items": [{
        "id": str(s.id), "type": s.type, "name": s.name, "connector_kind": s.connector_kind,
        "conn": conn(s), "status": s.status, "progress": s.config_json.get("progress"),
    } for s in rows]}


@router.post("/sources", status_code=201)
async def create_source(
    body: SourceIn, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    """Register a new external system (admin). Secrets go in
    config_json.auth.secret_env (resolved from server env), never stored raw."""
    if p.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    auth = (body.config_json.get("auth") or {}) if body.config_json else {}
    if auth.get("secret"):
        raise HTTPException(status_code=422,
                            detail="inline auth.secret not allowed — use auth.secret_env")
    src = DataSource(tenant_id=p.tenant_id, type=body.type, name=body.name,
                     connector_kind=body.connector_kind, conn=body.conn,
                     config_json=body.config_json, secret_ref=body.secret_ref,
                     status="connected")
    db.add(src)
    await db.commit()
    return {"id": str(src.id), "name": src.name, "status": src.status}


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    if p.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    src = await db.get(DataSource, source_id)
    if src is None or src.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="source not found")
    job_ids = (
        await db.execute(select(ExplorationJob.id).where(ExplorationJob.source_id == source_id))
    ).scalars().all()
    if job_ids:
        await db.execute(update(Operation).where(Operation.created_from_job_id.in_(job_ids))
                         .values(created_from_job_id=None))
        for model in (ExplorationEvent, DiscoveredOperation, DiscoveredEntity,
                      DiscoveredRule, DiscoveredChain):
            await db.execute(delete(model).where(model.job_id.in_(job_ids)))
        await db.execute(delete(ExplorationJob).where(ExplorationJob.id.in_(job_ids)))
    await db.delete(src)
    await db.commit()
    return {"deleted": str(source_id)}


@router.post("/sources/{source_id}/explore")
async def start_explore(
    source_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    if p.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    src = await db.get(DataSource, source_id)
    if src is None or src.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="source not found")
    job = ExplorationJob(source_id=src.id, tenant_id=p.tenant_id, trigger_type="manual",
                         status="queued", phase=0, progress=0,
                         started_at=datetime.now(timezone.utc))
    db.add(job)
    src.status = "running"
    await db.commit()
    # durable enqueue → handled by the arq worker (survives API restarts)
    try:
        pool = await get_pool()
        await pool.enqueue_job("explore_task", str(job.id))
    except Exception as exc:  # redis/worker unavailable → don't leave a phantom job
        job.status = "error"
        src.status = "error"
        await db.commit()
        raise HTTPException(status_code=503, detail=f"job queue unavailable: {exc}") from exc
    return {"job_id": str(job.id), "status": "queued"}


@router.get("/exploration-jobs/{job_id}")
async def get_job(
    job_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    job = await db.get(ExplorationJob, job_id)
    if job is None or job.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="job not found")
    return {"id": str(job.id), "source_id": str(job.source_id), "status": job.status,
            "phase": job.phase, "progress": job.progress}


@router.get("/exploration-jobs/{job_id}/events")
async def stream_events(
    job_id: uuid.UUID, request: Request,
    p: Principal = Depends(get_principal_qs), db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """SSE stream of exploration events; authed (query token for EventSource),
    tenant-scoped, resumable via Last-Event-ID."""
    job = await db.get(ExplorationJob, job_id)
    if job is None or job.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        last_seq = int(request.headers.get("last-event-id", "0") or "0")
    except ValueError:
        last_seq = 0

    async def gen():
        nonlocal last_seq
        while True:
            if await request.is_disconnected():
                break
            async with SessionLocal() as db:
                rows = (
                    await db.execute(
                        select(ExplorationEvent).where(
                            ExplorationEvent.job_id == job_id, ExplorationEvent.seq > last_seq
                        ).order_by(ExplorationEvent.seq)
                    )
                ).scalars().all()
                job = await db.get(ExplorationJob, job_id)
            for ev in rows:
                last_seq = ev.seq
                yield {"id": str(ev.seq), "event": ev.event_type,
                       "data": json.dumps(ev.payload_json, ensure_ascii=False)}
            if job and job.status in ("done", "error") and not rows:
                yield {"event": "close", "data": json.dumps({"status": job.status})}
                break
            await asyncio.sleep(0.5)

    return EventSourceResponse(gen())
