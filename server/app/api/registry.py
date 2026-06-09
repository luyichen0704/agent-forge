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

router = APIRouter(tags=["registry"])


async def _roles_for(db: AsyncSession, op_id: uuid.UUID) -> tuple[list[str], dict[str, str]]:
    perms = (
        await db.execute(select(OperationPermission).where(OperationPermission.operation_id == op_id))
    ).scalars().all()
    roles = [p.subject_id for p in perms if p.subject_type == "role" and p.effect == "allow"]
    scopes = {p.subject_id: p.condition_json.get("scope") for p in perms if p.condition_json.get("scope")}
    return roles, scopes


def _perm_label(roles: list[str]) -> str:
    rs = set(roles)
    if "customer" in rs:
        return "all"
    if "employee" in rs:
        return "emp+"
    return "admin"


async def _serialize(db: AsyncSession, op: Operation) -> dict:
    roles, scopes = await _roles_for(db, op.id)
    return {
        "id": str(op.id), "op_key": op.op_key, "version": op.version, "kind": op.kind,
        "confirm_level": op.confirm_level, "risk_level": op.risk_level, "status": op.status,
        "executor_binding": op.executor_binding, "policy_ref": op.policy_ref,
        "roles": roles, "perm": _perm_label(roles), "scopes": scopes,
    }


@router.get("/operations")
async def list_operations(
    p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    ops = (
        await db.execute(select(Operation).where(Operation.tenant_id == p.tenant_id).order_by(Operation.op_key))
    ).scalars().all()
    items = []
    for op in ops:
        data = await _serialize(db, op)
        # RBAC: non-admins only see operations their role may call
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
