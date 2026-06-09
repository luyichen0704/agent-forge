"""Executions — inspect + compensate (rollback) with real before/after."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import Principal, get_principal
from app.executors import get_executor
from app.models.execution import Execution
from app.models.audit import Trace
from app.services import audit

router = APIRouter(tags=["executions"])


@router.get("/traces/{trace_id}/executions")
async def list_executions(
    trace_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    t = await db.get(Trace, trace_id)
    if t is None or t.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="not found")
    if p.role == "customer" and t.actor_id != p.user.id:
        raise HTTPException(status_code=404, detail="not found")
    execs = (
        await db.execute(select(Execution).where(Execution.trace_id == trace_id))
    ).scalars().all()
    return {"items": [{"id": str(e.id), "op_key": e.op_key, "executor": e.executor,
                       "status": e.status, "before": e.before_state, "after": e.after_state,
                       "latency_ms": e.latency_ms, "error_code": e.error_code} for e in execs]}


@router.post("/executions/{execution_id}/rollback")
async def rollback_execution(
    execution_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    if p.role not in ("employee", "admin"):
        raise HTTPException(status_code=403, detail="not permitted")
    ex = await db.get(Execution, execution_id)
    if ex is None:
        raise HTTPException(status_code=404, detail="not found")
    t = await db.get(Trace, ex.trace_id)
    if t is None or t.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="not found")
    if ex.status == "rolled_back":
        raise HTTPException(status_code=409, detail="already rolled back")

    executor = get_executor(ex.executor)
    restored = await executor.rollback(db, ex.before_state, ex.after_state)

    comp = Execution(
        trace_id=ex.trace_id, op_key=ex.op_key + ".rollback", executor=ex.executor, status="ok",
        before_state=ex.after_state, after_state=restored,
        idempotency_key=f"rollback:{ex.id}", latency_ms=0, rolls_back_execution_id=ex.id,
    )
    db.add(comp)
    ex.status = "rolled_back"
    await audit.append_event(db, ex.trace_id, "EXECUTION_ROLLED_BACK",
                             {"op": ex.op_key, "compensation": True}, cap="write", actor_id=p.user.id)
    await db.commit()
    return {"ok": True, "compensation_id": str(comp.id), "restored": restored}
