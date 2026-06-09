"""CaMeL orchestrator — the agent harness wiring planner → policy → approvals →
executors → audit → dataflow into one governed turn.

Flow:
  create_plan():  Trace + P-LLM plan + policy review + (per write step) approval
                  requests + dataflow graph + audit events (up to CONFIRMATION_REQUESTED).
  confirm_plan(): once approvals satisfied → run executors, record executions,
                  append OPERATION_EXECUTED / DATAFLOW_SNAPSHOT / RESPONSE_SENT,
                  mark plan done.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ExecutionPlan, PlanStep
from app.models.execution import ApprovalRequest, ApprovalVote, Execution
from app.models.registry import Operation, OperationPermission
from app.models.audit import DataflowEdge, DataflowNode, Trace
from app.executors import get_executor
from app.policies.engine import Decision, Identity, StepCtx, evaluate_step
from app.services import audit, planner
from app.services.capabilities import Capability

CAP_FOR_KIND = {"query": "data", "parse": "parsed", "write": "write"}


async def _available_operations(db: AsyncSession, tenant_id: uuid.UUID, role: str) -> list[dict]:
    ops = (
        await db.execute(
            select(Operation).where(
                Operation.tenant_id == tenant_id, Operation.status == "active"
            )
        )
    ).scalars().all()
    out = []
    for op in ops:
        perms = (
            await db.execute(
                select(OperationPermission).where(OperationPermission.operation_id == op.id)
            )
        ).scalars().all()
        roles = [p.subject_id for p in perms if p.subject_type == "role" and p.effect == "allow"]
        out.append({
            "op_key": op.op_key, "kind": op.kind, "confirm_level": op.confirm_level,
            "roles": roles, "risk": op.risk_level, "desc": op.policy_ref or "",
            "executor": op.executor_binding,
            "scope": next((p.condition_json.get("scope") for p in perms if p.condition_json), None),
        })
    return out


async def create_plan(
    db: AsyncSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID,
    identity: Identity, instruction: str,
) -> ExecutionPlan:
    trace = Trace(
        tenant_id=tenant_id, title=instruction[:120], actor_id=uuid.UUID(identity.user_id),
        acting_role=identity.role, status="open",
    )
    db.add(trace)
    await db.flush()

    await audit.append_event(db, trace.id, "REQUEST_RECEIVED",
                             {"role": identity.role, "instruction": instruction},
                             cap="data", actor_id=uuid.UUID(identity.user_id))

    ops = await _available_operations(db, tenant_id, identity.role)
    op_by_key = {o["op_key"]: o for o in ops}
    draft = await planner.plan(db, trace.id, role=identity.role, instruction=instruction, operations=ops)

    await audit.append_event(db, trace.id, "PLAN_GENERATED",
                             {"intent": draft["intent"], "steps": len(draft["steps"]),
                              "llm_run_id": draft.get("_llm_run_id")}, cap="data")

    plan = ExecutionPlan(
        session_id=session_id, trace_id=trace.id, intent=draft["intent"], writes=draft["writes"],
        required_confirm_level=draft["required_confirm_level"], reasoning_summary=draft["reasoning_summary"],
        policy_hints_json={"hints": draft["policy_hints"]}, status="draft",
        pllm_run_id=uuid.UUID(draft["_llm_run_id"]) if draft.get("_llm_run_id") else None,
    )
    db.add(plan)
    await db.flush()

    # accumulate provenance through the plan
    running_cap = Capability.of("trusted")
    plan_required = "auto"
    from app.services.capabilities import stricter_confirm

    for s in draft["steps"]:
        op = op_by_key.get(s["op_key"] or "")
        step_cap = Capability.of(CAP_FOR_KIND.get(s["kind"], "data"))
        running_cap = running_cap.merge(step_cap)

        approval_id = None
        if s["kind"] == "write":
            ctx = StepCtx(
                op_key=s["op_key"] or "", op_kind="mutation",
                op_confirm=op["confirm_level"] if op else "confirm",
                risk=op["risk"] if op else "high",
                kwargs={}, arg_caps=running_cap,
                allowed_roles=op["roles"] if op else ["admin"],
                permission_scope=op.get("scope") if op else None,
            )
            decision = evaluate_step(identity, ctx)
            if decision.effect == "deny":
                await audit.append_event(db, trace.id, "POLICY_DENIED",
                                         {"op": s["op_key"], "reason": decision.reason}, cap="trusted")
                plan.status = "denied"
                await db.flush()
                return plan
            plan_required = stricter_confirm(plan_required, decision.required_confirm)
            req_votes = 2 if decision.required_confirm == "dual" else 1
            ar = ApprovalRequest(
                tenant_id=tenant_id, trace_id=trace.id, target_type="plan_step",
                target_id=s["op_key"] or "", confirm_level=decision.required_confirm,
                status="pending", requested_by=uuid.UUID(identity.user_id),
                required_votes=req_votes, expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
            db.add(ar)
            await db.flush()
            approval_id = ar.id

        db.add(PlanStep(
            plan_id=plan.id, step_no=s["step_no"], kind=s["kind"], op_key=s["op_key"],
            label=s["label"], capability_in=running_cap.as_list(), capability_out=s["capability_out"],
            approval_request_id=approval_id, status="planned",
        ))

    await audit.append_event(db, trace.id, "POLICY_EVALUATED",
                             {"required_confirm": plan_required}, cap="trusted")

    # derive dataflow graph from the plan
    await _build_dataflow(db, trace.id, instruction, draft["steps"])

    plan.required_confirm_level = plan_required
    if plan_required == "auto":
        plan.status = "confirmed"  # no human needed
    else:
        plan.status = "awaiting_confirm"
        await audit.append_event(db, trace.id, "CONFIRMATION_REQUESTED",
                                 {"level": plan_required, "writes": draft["writes"]}, cap="parsed")
    await db.flush()
    return plan


async def _build_dataflow(db, trace_id, instruction, steps):
    db.add(DataflowNode(trace_id=trace_id, node_id="n0", label=f'user_input("{instruction[:40]}")',
                        capability_set=["trusted"], source_kind="user", readers="all", via="可信通道"))
    prev = "n0"
    for s in steps:
        nid = f"n{s['step_no']}"
        db.add(DataflowNode(
            trace_id=trace_id, node_id=nid, label=s["label"],
            capability_set=[s["capability_out"]],
            source_kind=s["kind"], readers="emp, admin",
            via=("Q-LLM (无放宽)" if s["kind"] == "parse" else s.get("op_key") or s["kind"]),
        ))
        db.add(DataflowEdge(trace_id=trace_id, from_node_id=prev, to_node_id=nid,
                            transform_kind=s["kind"]))
        prev = nid


async def confirm_plan(db: AsyncSession, plan: ExecutionPlan, *, approver: Identity) -> ExecutionPlan:
    # lock the plan row → atomic state transition, no double execution
    plan = (
        await db.execute(select(ExecutionPlan).where(ExecutionPlan.id == plan.id).with_for_update())
    ).scalar_one()
    if plan.status not in ("awaiting_confirm", "confirmed"):
        return plan

    steps = (
        await db.execute(select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.step_no))
    ).scalars().all()

    # verify every write step's approval is satisfied
    for st in steps:
        if st.kind == "write" and st.approval_request_id:
            ar = await db.get(ApprovalRequest, st.approval_request_id)
            if ar.status != "approved":
                approvals = (
                    await db.execute(
                        select(ApprovalVote).where(
                            ApprovalVote.request_id == ar.id, ApprovalVote.decision == "approve"
                        )
                    )
                ).scalars().all()
                if len(approvals) < ar.required_votes:
                    return plan  # not yet executable

    await audit.append_event(db, plan.trace_id, "USER_CONFIRMED",
                             {"approver": approver.display_name or approver.user_id}, cap="trusted",
                             actor_id=uuid.UUID(approver.user_id))

    trace = await db.get(Trace, plan.trace_id)
    plan.status = "executing"
    ctx = await _execute_plan(db, plan, trace, steps)

    had_error = any(st.status == "error" for st in steps)
    await audit.append_event(db, plan.trace_id, "DATAFLOW_SNAPSHOT", {"steps": len(steps)}, cap="data")
    await audit.append_event(db, plan.trace_id, "RESPONSE_SENT",
                             {"status": "partial_failed" if had_error else "done"}, cap="data")
    plan.status = "partial_failed" if had_error else "done"
    trace.status = "open" if had_error else "closed"
    await db.flush()
    return plan


async def _execute_plan(db: AsyncSession, plan: ExecutionPlan, trace: Trace, steps: list[PlanStep]) -> dict:
    """Run the steps. query→read, parse→Q-LLM, write→executor with resolved args.
    Returns the runtime context of step outputs (overridden in Batch 3 wiring)."""
    ctx: dict = {}
    for st in steps:
        if st.kind != "write" or not st.op_key:
            st.status = "done"
            continue
        op = (
            await db.execute(
                select(Operation).where(
                    Operation.tenant_id == trace.tenant_id, Operation.op_key == st.op_key
                ).order_by(Operation.version.desc())
            )
        ).scalars().first()
        ex = get_executor(op.executor_binding if op else None)
        idem = f"{plan.id}:{st.step_no}"
        # idempotency: reuse a prior successful execution with the same key
        existing = (
            await db.execute(select(Execution).where(Execution.idempotency_key == idem))
        ).scalar_one_or_none()
        if existing is not None:
            st.status = "done" if existing.status == "ok" else "error"
            continue
        kwargs = dict(st.input_refs_json or {})
        started = datetime.now(timezone.utc)
        res = await ex.execute(db, trace.tenant_id, st.op_key, kwargs)
        latency = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        db.add(Execution(
            trace_id=plan.trace_id, plan_step_id=st.id, op_key=st.op_key,
            executor=ex.name, status="error" if res.error_code else "ok",
            before_state=res.before_state, after_state=res.after_state,
            idempotency_key=idem, latency_ms=latency, error_code=res.error_code,
        ))
        st.status = "done" if not res.error_code else "error"
        await audit.append_event(db, plan.trace_id, "OPERATION_EXECUTED",
                                 {"op": st.op_key, "executor": ex.name, "latency_ms": latency,
                                  "error": res.error_code}, cap="write")
    return ctx
