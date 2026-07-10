"""Operation Registry — versioned operations, server-enforced permissions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import Principal, get_principal
from app.models.registry import Operation, OperationPermission
from app.models.sources import DataSource

router = APIRouter(tags=["registry"])


def _perm_label(roles: list[str]) -> str:
    rs = set(roles)
    if "customer" in rs:
        return "all"
    if "employee" in rs:
        return "emp+"
    return "admin"


def _serialize_with(op: Operation, perms: list[OperationPermission],
                    source_name: str | None = None) -> dict:
    roles = [p.subject_id for p in perms if p.subject_type == "role" and p.effect == "allow"]
    scopes = {p.subject_id: p.condition_json.get("scope") for p in perms if p.condition_json.get("scope")}
    binding = op.binding_json or {}
    return {
        "id": str(op.id), "op_key": op.op_key, "version": op.version, "kind": op.kind,
        "confirm_level": op.confirm_level, "risk_level": op.risk_level, "status": op.status,
        "executor_binding": op.executor_binding, "policy_ref": op.policy_ref,
        "roles": roles, "perm": _perm_label(roles), "scopes": scopes,
        "source_id": str(op.source_id) if op.source_id else None,
        "source_name": source_name,
        "desc": (op.input_schema_json or {}).get("desc", ""),
        "call": (f"{binding.get('method')} {binding.get('path')}"
                 if binding.get("path") else None),
    }


async def _serialize(db: AsyncSession, op: Operation) -> dict:
    perms = (
        await db.execute(select(OperationPermission).where(OperationPermission.operation_id == op.id))
    ).scalars().all()
    return _serialize_with(op, list(perms))


@router.get("/operations")
async def list_operations(
    source_id: uuid.UUID | None = None,
    p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    q = select(Operation).where(Operation.tenant_id == p.tenant_id)
    if source_id is not None:
        q = q.where(Operation.source_id == source_id)
    ops = (await db.execute(q.order_by(Operation.op_key))).scalars().all()
    # batch-load permissions + source names for all ops at once (no per-op N+1)
    op_ids = [op.id for op in ops]
    perms_by_op: dict = {}
    if op_ids:
        perms = (
            await db.execute(select(OperationPermission).where(OperationPermission.operation_id.in_(op_ids)))
        ).scalars().all()
        for pm in perms:
            perms_by_op.setdefault(pm.operation_id, []).append(pm)
    src_ids = {op.source_id for op in ops if op.source_id}
    names: dict = {}
    if src_ids:
        rows = (await db.execute(select(DataSource.id, DataSource.name)
                                 .where(DataSource.id.in_(src_ids)))).all()
        names = {sid: name for sid, name in rows}
    items = []
    for op in ops:
        data = _serialize_with(op, perms_by_op.get(op.id, []), names.get(op.source_id))
        if p.role != "admin" and p.role not in data["roles"]:
            continue
        items.append(data)
    pending = sum(1 for o in items if o["status"] == "pending")
    return {"items": items, "pending_count": pending, "total": len(items)}


@router.get("/operations/{op_id}")
async def get_operation(
    op_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    op = await db.get(Operation, op_id)
    if op is None or op.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="not found")
    data = await _serialize(db, op)
    if p.role != "admin" and p.role not in data["roles"]:
        raise HTTPException(status_code=404, detail="not found")
    return data


def _require_admin(p: Principal) -> None:
    if p.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")


@router.post("/operations/{op_id}/publish")
async def publish_operation(
    op_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    _require_admin(p)
    op = await db.get(Operation, op_id)
    if op is None or op.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="not found")
    op.status = "active"
    op.published_at = datetime.now(timezone.utc)
    await db.commit()
    return await _serialize(db, op)


@router.post("/operations/{op_id}/disable")
async def disable_operation(
    op_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    _require_admin(p)
    op = await db.get(Operation, op_id)
    if op is None or op.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="not found")
    op.status = "disabled"
    await db.commit()
    return await _serialize(db, op)
