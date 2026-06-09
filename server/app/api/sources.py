"""Data sources + exploration jobs (SSE live stream)."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.db import SessionLocal, get_db
from app.deps import Principal, get_principal, get_principal_qs
from app.models.sources import DataSource, ExplorationEvent, ExplorationJob
from app.services.explorer import run_exploration

router = APIRouter(tags=["sources"])


@router.get("/sources")
async def list_sources(p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (
        await db.execute(select(DataSource).where(DataSource.tenant_id == p.tenant_id).order_by(DataSource.created_at))
    ).scalars().all()
    return {"items": [{
        "id": str(s.id), "type": s.type, "name": s.name, "connector_kind": s.connector_kind,
        "conn": s.conn, "status": s.status, "progress": s.config_json.get("progress"),
    } for s in rows]}


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
                         status="running", phase=1, progress=0,
                         started_at=datetime.now(timezone.utc))
    db.add(job)
    src.status = "running"
    await db.commit()
    # fire-and-forget background exploration (own DB session inside)
    asyncio.create_task(run_exploration(job.id))
    return {"job_id": str(job.id), "status": "running"}


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
