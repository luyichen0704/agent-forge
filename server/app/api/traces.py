"""Traces — shared correlation across flow / audit / executions."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import Principal, get_principal
from app.models.audit import AuditEvent, DataflowEdge, DataflowNode, Trace
from app.services import audit

router = APIRouter(tags=["traces"])


@router.get("/traces")
async def list_traces(p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)) -> dict:
    q = select(Trace).where(Trace.tenant_id == p.tenant_id)
    # customers may only ever see their own traces (not the whole tenant's)
    if p.role == "customer":
        q = q.where(Trace.actor_id == p.user.id)
    traces = (await db.execute(q.order_by(Trace.created_at.desc()).limit(50))).scalars().all()
    return {"items": [{"id": str(t.id), "title": t.title, "status": t.status,
                       "acting_role": t.acting_role, "created_at": t.created_at.isoformat()} for t in traces]}


async def _owned_trace(db: AsyncSession, p: Principal, trace_id: uuid.UUID) -> Trace:
    t = await db.get(Trace, trace_id)
    if t is None or t.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="trace not found")
    # customers can only read their own traces; employee/admin see tenant-level
    if p.role == "customer" and t.actor_id != p.user.id:
        raise HTTPException(status_code=404, detail="trace not found")
    return t


@router.get("/traces/{trace_id}/flow")
async def trace_flow(
    trace_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    await _owned_trace(db, p, trace_id)
    nodes = (
        await db.execute(select(DataflowNode).where(DataflowNode.trace_id == trace_id))
    ).scalars().all()
    edges = (
        await db.execute(select(DataflowEdge).where(DataflowEdge.trace_id == trace_id))
    ).scalars().all()
    return {
        "trace_id": str(trace_id),
        "nodes": [{"node_id": n.node_id, "label": n.label, "cap": (n.capability_set or ["data"])[0],
                   "capability_set": n.capability_set, "source": n.source_kind, "readers": n.readers,
                   "via": n.via} for n in nodes],
        "edges": [{"from": e.from_node_id, "to": e.to_node_id, "kind": e.transform_kind} for e in edges],
    }


@router.get("/traces/{trace_id}/audit")
async def trace_audit(
    trace_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    await _owned_trace(db, p, trace_id)
    events = (
        await db.execute(
            select(AuditEvent).where(AuditEvent.trace_id == trace_id).order_by(AuditEvent.seq)
        )
    ).scalars().all()
    verification = await audit.verify_chain(db, trace_id)
    return {
        "trace_id": str(trace_id),
        "verification": verification,
        "events": [{"seq": e.seq, "event": e.event_type, "cap": e.cap, "payload": e.payload_json,
                    "hash": e.hash, "prev_hash": e.prev_hash,
                    "created_at": e.created_at.isoformat()} for e in events],
    }
