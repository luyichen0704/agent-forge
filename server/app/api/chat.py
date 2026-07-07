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
from app.models.chat import PlanStep

# write-intent verbs — a request naming one of these expects a create/change
_WRITE_INTENT = ("新建", "创建", "建一个", "建个", "添加", "新增", "增加", "修改", "更新",
                 "改成", "删除", "移除", "发送", "发布", "开通", "创建一个", "录入", "登记",
                 "create", "add", "update", "delete", "send", "publish", "new ")


def _looks_like_write(text: str) -> bool:
    t = text.lower()
    return any(w in text or w in t for w in _WRITE_INTENT)
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


class SessionIn(BaseModel):
    title: str | None = None
    source_id: uuid.UUID | None = None  # scope planning to one system (optional)


@router.post("/chat/sessions")
async def create_session(
    body: SessionIn | None = None,
    p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db),
) -> dict:
    body = body or SessionIn()
    s = ChatSession(tenant_id=p.tenant_id, user_id=p.user.id,
                    title=(body.title or "新会话")[:160], source_id=body.source_id)
    db.add(s)
    await db.commit()
    return {"id": str(s.id), "title": s.title, "source_id": str(s.source_id) if s.source_id else None}


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
                "created_at": m.created_at.isoformat(), "plan": None}
        if m.plan_id:
            plan = await db.get(ExecutionPlan, m.plan_id)
            if plan:
                item["plan"] = await _serialize_plan(db, plan)
        out.append(item)
    return {"items": out}


class MessageIn(BaseModel):
    content: str


# transport-envelope noise that means nothing to a business user
_NOISE_KEYS = {"success", "message", "code", "msg", "status", "error", "errors",
               "total", "page", "page_size", "per_page", "count"}


def _human_row(r: dict) -> str:
    pairs = []
    for k, v in r.items():
        if k in _NOISE_KEYS or isinstance(v, (dict, list)):
            continue  # skip envelope noise + nested structures
        s = str(v)
        if s == "":
            continue
        pairs.append(f"{k}: {s[:40] + '…' if len(s) > 40 else s}")
        if len(pairs) >= 4:
            break
    if not pairs:  # fall back to whatever scalar fields exist (still skip noise)
        for k, v in list(r.items())[:4]:
            if k not in _NOISE_KEYS and not isinstance(v, (dict, list)) and str(v) != "":
                pairs.append(f"{k}: {str(v)[:40]}")
                if len(pairs) >= 3:
                    break
    return "，".join(pairs) or "（1 条记录）"


def _result_reply(plan) -> str:
    """Plain-language execution summary for domain experts (no tech jargon)."""
    ctx = getattr(plan, "exec_context", None)
    if not ctx:
        return f"已完成：{plan.intent}"
    rows = ctx.get("rows") or []
    steps = ctx.get("steps") or []
    errors = ctx.get("query_errors") or []
    lines: list[str] = []
    queries = [s for s in steps if s["kind"] == "query"]
    writes = [s for s in steps if s["kind"] == "write"]
    if queries:
        real_rows = [r for r in rows if not (isinstance(r, dict) and set(r) == {"error"})]
        if real_rows:
            lines.append(f"查询完成，共找到 {len(real_rows)} 条数据，例如：")
            lines += [f"· {_human_row(r)}" for r in real_rows[:3]]
            if len(real_rows) > 3:
                lines.append(f"（其余 {len(real_rows) - 3} 条可在「数据流」页查看）")
        elif "not_connected" in errors:
            lines.append("这个操作还没有连通到真实系统（尚未完成对接），所以查不到数据。请联系管理员完成该系统的对接后再试。")
        elif errors:
            lines.append("查询时访问业务系统失败了（已记录详细原因，可在「审计」页查看）。可能是目标不存在或参数不对，请换个条件或联系管理员。")
        else:
            lines.append("查询完成，但没有找到符合条件的数据。可以换个说法或放宽条件再试。")
    for s in writes:
        if s["status"] == "done":
            lines.append(f"✅ 已完成：{s['label']}")
        else:
            lines.append(f"⚠️ 未成功：{s['label']}。失败原因已记录在「审计」页，数据没有被改动。")
    return "\n".join(lines) or f"已完成：{plan.intent}"


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

    now = datetime.now(timezone.utc)
    db.add(ChatMessage(session_id=session_id, role="user", content=body.content, created_at=now))
    if s.title == "新会话":
        s.title = body.content.strip()[:40]
    await db.flush()

    plan = await orchestrator.create_plan(
        db, tenant_id=p.tenant_id, session_id=session_id,
        identity=p.identity, instruction=body.content, source_id=s.source_id,
    )

    n_steps = len((
        await db.execute(select(PlanStep).where(PlanStep.plan_id == plan.id))
    ).scalars().all())
    # write intent in the request but the plan has no write step → the system
    # exposes no matching write operation; say so honestly instead of masking it.
    wants_write = _looks_like_write(body.content)
    write_note = ("这个系统目前只开通了查询类操作，还不能执行新建/修改，已按查询处理。"
                  "如需真正写入，请联系管理员开通对应的写操作。\n\n"
                  if (wants_write and plan.writes == 0 and n_steps) else "")

    if plan.status == "denied":
        reply = "这个请求超出了你的权限范围，没有执行。如需办理，请联系管理员开通相应权限。"
    elif not n_steps:
        reply = ("这个系统里目前没有能满足这个请求的功能，所以没有执行。"
                 + ("如果你需要新建/修改类操作，请联系管理员开通对应的写操作。" if wants_write else
                    "可以换种问法，或让管理员确认该系统是否已开通相关能力。"))
    elif plan.required_confirm_level == "auto":
        # no human gate → execute the (read-only) plan now and report truthfully
        plan = await orchestrator.confirm_plan(db, plan, approver=p.identity)
        reply = write_note + (_result_reply(plan) if plan.status == "done"
                 else f"已生成方案，但执行没有完全成功。{_result_reply(plan)}".strip())
    elif plan.required_confirm_level == "dual":
        reply = (f"我准备好了这个方案（含 {plan.writes} 个修改动作）。这类操作影响较大，"
                 "需要另一位管理员在「审批」页同意后，你再点「确认执行」。")
    else:
        reply = (f"我准备好了这个方案（含 {plan.writes} 个修改动作）。"
                 "请核对下方步骤，点「确认执行」后才会真正生效。")

    plan_data = await _serialize_plan(db, plan)

    db.add(ChatMessage(session_id=session_id, role="assistant", content=reply,
                       plan_id=plan.id, created_at=datetime.now(timezone.utc)))
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
    reply = None
    if plan.status in ("done", "partial_failed") and getattr(plan, "exec_context", None):
        # surface the real outcome in the conversation, in plain language
        reply = _result_reply(plan)
        db.add(ChatMessage(session_id=plan.session_id, role="assistant", content=reply,
                           plan_id=plan.id, created_at=datetime.now(timezone.utc)))
    await db.commit()
    data = await _serialize_plan(db, plan)
    data["blocked"] = plan.status not in ("done", "executing")
    if reply:
        data["reply"] = reply
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
