"""Approval requests + votes — real dual_approval state machine."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import Principal, get_principal
from app.models.execution import ApprovalRequest, ApprovalVote
from app.services import audit

router = APIRouter(tags=["approvals"])


async def _serialize(db: AsyncSession, ar: ApprovalRequest) -> dict:
    votes = (
        await db.execute(select(ApprovalVote).where(ApprovalVote.request_id == ar.id))
    ).scalars().all()
    approvals = [v for v in votes if v.decision == "approve"]
    return {
        "id": str(ar.id), "trace_id": str(ar.trace_id) if ar.trace_id else None,
        "target_type": ar.target_type, "target_id": ar.target_id,
        "confirm_level": ar.confirm_level, "status": ar.status,
        "required_votes": ar.required_votes, "approve_votes": len(approvals),
        "votes": [{"approver_id": str(v.approver_id), "decision": v.decision,
                   "comment": v.comment, "created_at": v.created_at.isoformat()} for v in votes],
    }


@router.get("/approval-requests")
async def list_requests(
    status: str | None = None, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    q = select(ApprovalRequest).where(ApprovalRequest.tenant_id == p.tenant_id)
    if status:
        q = q.where(ApprovalRequest.status == status)
    reqs = (await db.execute(q.order_by(ApprovalRequest.created_at.desc()))).scalars().all()
    return {"items": [await _serialize(db, r) for r in reqs]}


class VoteIn(BaseModel):
    decision: Literal["approve", "reject"] = "approve"
    comment: str = ""


@router.post("/approval-requests/{req_id}/votes")
async def cast_vote(
    req_id: uuid.UUID, body: VoteIn,
    p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db),
) -> dict:
    if p.role != "admin":
        raise HTTPException(status_code=403, detail="only admins may vote on approvals")
    # lock the request row so concurrent votes resolve the state machine atomically
    ar = (
        await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == req_id).with_for_update())
    ).scalar_one_or_none()
    if ar is None or ar.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="not found")
    if ar.status != "pending":
        raise HTTPException(status_code=409, detail=f"request already {ar.status}")
    if ar.expires_at and ar.expires_at < datetime.now(timezone.utc):
        ar.status = "expired"
        await db.commit()
        raise HTTPException(status_code=409, detail="approval request expired")
    # the requester may not approve their own high-risk request
    if ar.requested_by == p.user.id and body.decision == "approve":
        raise HTTPException(status_code=403, detail="requester cannot self-approve")

    # one vote per approver (DB unique constraint also guards this)
    existing = (
        await db.execute(
            select(ApprovalVote).where(
                ApprovalVote.request_id == ar.id, ApprovalVote.approver_id == p.user.id
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="you have already voted")

    db.add(ApprovalVote(request_id=ar.id, approver_id=p.user.id, decision=body.decision,
                        comment=body.comment, created_at=datetime.now(timezone.utc)))
    await db.flush()

    if body.decision == "reject":
        ar.status = "rejected"
    else:
        approvals = (
            await db.execute(
                select(ApprovalVote).where(
                    ApprovalVote.request_id == ar.id, ApprovalVote.decision == "approve"
                )
            )
        ).scalars().all()
        if len(approvals) >= ar.required_votes:
            ar.status = "approved"

    if ar.trace_id:
        await audit.append_event(db, ar.trace_id, "APPROVAL_VOTE",
                                 {"decision": body.decision, "status": ar.status,
                                  "target": ar.target_id}, cap="trusted", actor_id=p.user.id)
    await db.commit()
    return await _serialize(db, ar)
