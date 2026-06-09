"""Chat — sessions, messages, and plan lifecycle (P-LLM → policy → execute)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator
from app.db import get_db
from app.deps import Principal, get_principal
from app.models.chat import ChatMessage, ChatSession, ExecutionPlan, PlanStep

router = APIRouter(tags=["chat"])


async def _serialize_plan(db: AsyncSession, plan: ExecutionPlan) -> dict:
    steps = (
        await db.execute(select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.step_no))
    ).scalars().all()
    return {
        "id": str(plan.id), "trace_id": str(plan.trace_id), "intent": plan.intent,
        "writes": plan.writes, "required_confirm_level": plan.required_confirm_level,
        "status": plan.status, "reasoning_summary": plan.reasoning_summary,
        "policy_hints": plan.policy_hints_json.get("hints", []),
        "steps": [{"step_no": s.step_no, "kind": s.kind, "op_key": s.op_key, "label": s.label,
                   "capability_in": s.capability_in, "capability_out": s.capability_out,
                   "approval_request_id": str(s.approval_request_id) if s.approval_request_id else None,
                   "status": s.status} for s in steps],
    }


@router.get("/chat/sessions")
async def list_sessions(p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (
        await db.execute(
            select(ChatSession).where(ChatSession.user_id == p.user.id)
            .order_by(ChatSession.created_at.desc())
        )
    ).scalars().all()
    return {"items": [{"id": str(s.id), "title": s.title} for s in rows]}


@router.post("/chat/sessions")
async def create_session(p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)) -> dict:
    s = ChatSession(tenant_id=p.tenant_id, user_id=p.user.id, title="新会话")
    db.add(s)
    await db.commit()
    return {"id": str(s.id), "title": s.title}


@router.get("/chat/sessions/{session_id}/messages")
async def get_messages(
    session_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    s = await db.get(ChatSession, session_id)
    if s is None or s.user_id != p.user.id:
        raise HTTPException(status_code=404, detail="session not found")
    msgs = (
        await db.execute(
            select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
        )
    ).scalars().all()
    out = []
    for m in msgs:
        item = {"id": str(m.id), "role": m.role, "content": m.content,
                "created_at": m.created_at, "plan": None}
        if m.plan_id:
            plan = await db.get(ExecutionPlan, m.plan_id)
            if plan:
                item["plan"] = await _serialize_plan(db, plan)
        out.append(item)
    return {"items": out}


class MessageIn(BaseModel):
    content: str


@router.post("/chat/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID, body: MessageIn,
    p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db),
) -> dict:
    s = await db.get(ChatSession, session_id)
    if s is None or s.user_id != p.user.id:
        raise HTTPException(status_code=404, detail="session not found")
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="empty message")

    now = datetime.now(timezone.utc).isoformat()
    db.add(ChatMessage(session_id=session_id, role="user", content=body.content, created_at=now))
    if s.title == "新会话":
        s.title = body.content.strip()[:40]
    await db.flush()

    plan = await orchestrator.create_plan(
        db, tenant_id=p.tenant_id, session_id=session_id,
        identity=p.identity, instruction=body.content,
    )

    if plan.status == "denied":
        reply = "该请求被策略拒绝，未生成可执行计划。"
    elif plan.required_confirm_level == "auto":
        # no human gate → execute the (read-only) plan now and report truthfully
        plan = await orchestrator.confirm_plan(db, plan, approver=p.identity)
        reply = (f"已规划并执行：{plan.intent}" if plan.status == "done"
                 else f"已规划，但执行未完全成功（{plan.status}）。")
    else:
        reply = f"我将执行以下操作，涉及 {plan.writes} 个写操作，需要确认（{plan.required_confirm_level}）。"

    plan_data = await _serialize_plan(db, plan)

    db.add(ChatMessage(session_id=session_id, role="assistant", content=reply,
                       plan_id=plan.id, created_at=datetime.now(timezone.utc).isoformat()))
    await db.commit()
    return {"reply": reply, "plan": plan_data}


async def _owned_plan(db: AsyncSession, p: Principal, plan_id: uuid.UUID) -> ExecutionPlan:
    """Load a plan, enforcing tenant + ownership (or admin). Prevents IDOR."""
    plan = await db.get(ExecutionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    sess = await db.get(ChatSession, plan.session_id)
    if sess is None or sess.tenant_id != p.tenant_id:
        raise HTTPException(status_code=404, detail="plan not found")
    if sess.user_id != p.user.id and not p.is_admin:
        # don't leak existence to other users
        raise HTTPException(status_code=404, detail="plan not found")
    return plan


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    plan = await _owned_plan(db, p, plan_id)
    return await _serialize_plan(db, plan)


@router.post("/plans/{plan_id}/confirm")
async def confirm_plan(
    plan_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    plan = await _owned_plan(db, p, plan_id)
    plan = await orchestrator.confirm_plan(db, plan, approver=p.identity)
    await db.commit()
    data = await _serialize_plan(db, plan)
    data["blocked"] = plan.status not in ("done", "executing")
    return data


@router.post("/plans/{plan_id}/cancel")
async def cancel_plan(
    plan_id: uuid.UUID, p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> dict:
    plan = await _owned_plan(db, p, plan_id)
    if plan.status in ("draft", "awaiting_confirm", "confirmed"):
        plan.status = "cancelled"
        await db.commit()
    return {"id": str(plan.id), "status": plan.status}
