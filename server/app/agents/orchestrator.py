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

import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ExecutionPlan, PlanStep
from app.models.execution import ApprovalRequest, ApprovalVote, Execution
from app.models.policy import PolicyRule
from app.models.registry import Operation, OperationPermission
from app.models.audit import DataflowEdge, DataflowNode, Trace
from app.executors import get_executor
from app.policies.engine import Decision, Identity, StepCtx, evaluate_step
from app.services import audit, planner, qparser
from app.services.capabilities import Capability

CAP_FOR_KIND = {"query": "data", "parse": "parsed", "write": "write"}


async def _available_operations(db: AsyncSession, tenant_id: uuid.UUID, role: str,
                                source_id: uuid.UUID | None = None) -> list[dict]:
    q = select(Operation).where(Operation.tenant_id == tenant_id, Operation.status == "active")
    if source_id is not None:
        # scope the catalogue to the session's system so the P-LLM can't pick an
        # operation belonging to a different registered system
        q = q.where(Operation.source_id == source_id)
    ops = (await db.execute(q)).scalars().all()
    op_ids = [op.id for op in ops]
    perms_by_op: dict = {}
    if op_ids:
        perms = (
            await db.execute(select(OperationPermission).where(OperationPermission.operation_id.in_(op_ids)))
        ).scalars().all()
        for pm in perms:
            perms_by_op.setdefault(pm.operation_id, []).append(pm)
    out = []
    for op in ops:
        # skip unbound API aliases: an APIExecutor op with no real binding is a
        # metadata-only leftover (e.g. a duplicate name the probe never grounded).
        # Keeping it lets the planner route a query to a dead endpoint → the
        # bound sibling never runs. FunctionExecutor demo ops (no binding) stay.
        if op.executor_binding == "APIExecutor" and not op.binding_json:
            continue
        perms = perms_by_op.get(op.id, [])
        roles = [p.subject_id for p in perms if p.subject_type == "role" and p.effect == "allow"]
        schema = op.input_schema_json or {}
        params = schema.get("params") or {}
        sig = ", ".join(
            f"{n}({v.get('in', 'query')}{'*' if v.get('required') else ''})"
            for n, v in list(params.items())[:8]
        )
        body = ", ".join(schema.get("body_fields") or [])
        out.append({
            "op_key": op.op_key, "kind": op.kind, "confirm_level": op.confirm_level,
            "roles": roles, "risk": op.risk_level,
            "desc": schema.get("desc") or op.policy_ref or "",
            "sig": sig, "body": body,
            "executor": op.executor_binding,
            "scope": next((p.condition_json.get("scope") for p in perms if p.condition_json), None),
        })
    return out


async def _eligible_admin_count(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    from app.models.identity import Role, User, UserRole
    rows = (
        await db.execute(
            select(User.id).join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(User.tenant_id == tenant_id, Role.key == "admin", User.is_active.is_(True))
        )
    ).scalars().all()
    return len(set(rows))


async def create_plan(
    db: AsyncSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID,
    identity: Identity, instruction: str, source_id: uuid.UUID | None = None,
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

    ops = await _available_operations(db, tenant_id, identity.role, source_id)
    op_by_key = {o["op_key"]: o for o in ops}
    draft = await planner.plan(db, trace.id, tenant_id=tenant_id, role=identity.role,
                               instruction=instruction, operations=ops)

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

    eligible_admins = await _eligible_admin_count(db, tenant_id)

    # Load active database PolicyRules for this tenant (AgentGuard pattern)
    db_rules = (
        await db.execute(
            select(PolicyRule).where(
                PolicyRule.tenant_id == tenant_id, PolicyRule.status == "active"
            )
        )
    ).scalars().all()

    for s in draft["steps"]:
        op = op_by_key.get(s["op_key"] or "")
        step_cap = Capability.of(CAP_FOR_KIND.get(s["kind"], "data"))
        running_cap = running_cap.merge(step_cap)

        # run policy for EVERY step so identity constraints (e.g. customer
        # self-scope) are computed and persisted, not just for writes.
        ctx = StepCtx(
            op_key=s["op_key"] or "", op_kind=("mutation" if s["kind"] == "write" else "query"),
            op_confirm=op["confirm_level"] if op else ("confirm" if s["kind"] == "write" else "auto"),
            risk=op["risk"] if op else ("high" if s["kind"] == "write" else "low"),
            kwargs={}, arg_caps=running_cap,
            allowed_roles=op["roles"] if op else (["admin"] if s["kind"] == "write" else
                                                  ["customer", "employee", "admin"]),
            permission_scope=op.get("scope") if op else None,
        )
        decision = evaluate_step(identity, ctx, db_rules=list(db_rules))
        if decision.effect == "deny":
            await audit.append_event(db, trace.id, "POLICY_DENIED",
                                     {"op": s["op_key"], "reason": decision.reason,
                                      "rule_source": "db"}, cap="trusted")
            plan.status = "denied"
            await db.flush()
            return plan

        # persisted, server-trusted args: planner's args + policy-injected scope
        step_args = dict(s.get("args") or {})
        step_args.update(decision.injected)  # e.g. user_id forced to caller for customer

        approval_id = None
        if s["kind"] == "write":
            plan_required = stricter_confirm(plan_required, decision.required_confirm)
            # `confirm` = the plan owner's own confirmation is the gate (no separate vote).
            # `dual` = TWO distinct admins in total. The requester cannot vote on their
            # own request, so an admin requester counts as the first of the two pairs
            # of eyes and one independent admin vote remains (four-eyes principle).
            if decision.required_confirm == "dual":
                ar = ApprovalRequest(
                    tenant_id=tenant_id, trace_id=trace.id, target_type="plan_step",
                    target_id=s["op_key"] or "", confirm_level="dual",
                    status="pending", requested_by=uuid.UUID(identity.user_id),
                    required_votes=1 if identity.role == "admin" else 2,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                )
                db.add(ar)
                await db.flush()
                approval_id = ar.id

        db.add(PlanStep(
            plan_id=plan.id, step_no=s["step_no"], kind=s["kind"], op_key=s["op_key"],
            label=s["label"], capability_in=running_cap.as_list(), capability_out=s["capability_out"],
            approval_request_id=approval_id, status="planned", input_refs_json=step_args,
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
        # the requester cannot vote on their own request — exclude them
        independent = eligible_admins - (1 if identity.role == "admin" else 0)
        needed = (1 if identity.role == "admin" else 2)
        await audit.append_event(db, trace.id, "CONFIRMATION_REQUESTED",
                                 {"level": plan_required, "writes": draft["writes"],
                                  "eligible_admins": eligible_admins,
                                  "satisfiable": plan_required != "dual" or independent >= needed},
                                 cap="parsed")
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
    try:
        ctx = await _execute_plan(db, plan, trace, steps)
    except Exception as exc:  # noqa: BLE001 — a broken plan shape must fail
        # gracefully (honest failure), never surface a raw 500. Mark the plan
        # failed, record the reason, and let the caller show a plain-language error.
        plan_id = plan.id
        await db.rollback()
        with db.no_autoflush:  # don't re-flush the failed state during the re-query
            plan = (await db.execute(
                select(ExecutionPlan).where(ExecutionPlan.id == plan_id).with_for_update())).scalar_one()
        plan.status = "failed"
        trace = await db.get(Trace, plan.trace_id)
        if trace:
            trace.status = "open"
        await audit.append_event(db, plan.trace_id, "EXECUTION_FAILED",
                                 {"error": f"{type(exc).__name__}: {exc}"[:200]}, cap="trusted")
        plan.exec_context = {"rows": [], "selected": [], "query_errors": ["plan_execution_failed"],
                             "steps": [], "fatal": f"{type(exc).__name__}"}
        await db.flush()
        return plan

    had_error = any(st.status == "error" for st in steps)
    await audit.append_event(db, plan.trace_id, "DATAFLOW_SNAPSHOT", {"steps": len(steps)}, cap="data")
    await audit.append_event(db, plan.trace_id, "RESPONSE_SENT",
                             {"status": "partial_failed" if had_error else "done"}, cap="data")
    plan.status = "partial_failed" if had_error else "done"
    trace.status = "open" if had_error else "closed"
    await db.flush()
    # expose execution results to the caller (chat reply summarization) without
    # persisting raw data on the plan row
    plan.exec_context = {**ctx, "steps": [
        {"step_no": st.step_no, "kind": st.kind, "op_key": st.op_key,
         "label": st.label, "status": st.status} for st in steps
    ]}
    return plan


async def _load_op(db: AsyncSession, tenant_id: uuid.UUID, op_key: str) -> Operation | None:
    return (
        await db.execute(
            select(Operation).where(Operation.tenant_id == tenant_id, Operation.op_key == op_key)
            .order_by(Operation.version.desc())
        )
    ).scalars().first()


async def _op_executor(db: AsyncSession, tenant_id: uuid.UUID, op_key: str):
    op = await _load_op(db, tenant_id, op_key)
    return get_executor(op.executor_binding if op else None)


def _row_id(row: dict) -> str | None:
    """Best-effort record identifier across arbitrary systems."""
    for k in ("id", "key", "uuid", "uid", "name", "slug"):
        if row.get(k) not in (None, ""):
            return str(row[k])
    return None


_REF_RE = re.compile(r"^\$(?:step)?(\d+|prev)(?:\.([A-Za-z0-9_]+))?$")


def _resolve_refs(kwargs: dict, step_rows: dict[int, list[dict]]) -> dict:
    """Resolve planner-emitted cross-step references in arg values, e.g.
    "$step1.base_id" → the base_id field of step 1's first output row, "$step2"
    → step 2's first row id. Target-agnostic; unresolved refs are left as-is so
    the failure surfaces at the executor rather than being silently dropped."""
    def resolve_one(v):
        if isinstance(v, str):
            m = _REF_RE.match(v.strip())
            if not m:
                return v
            which, field = m.group(1), m.group(2)
            if which == "prev":
                rows = step_rows[max(step_rows)] if step_rows else []
            else:
                rows = step_rows.get(int(which), [])
            if not rows:
                return v
            row = rows[0]
            if field:
                return row.get(field, v)
            return _row_id(row) or v
        if isinstance(v, list):
            return [resolve_one(x) for x in v]
        return v
    return {k: resolve_one(v) for k, v in kwargs.items()}


def _id_params(op: Operation | None) -> list[str]:
    """Parameter names of an operation that look like a record identifier
    (declared `id` or `*_id`), path params first — target-agnostic."""
    schema = (op.input_schema_json if op else None) or {}
    params = schema.get("params") or {}
    idish = [n for n in params if n == "id" or n.endswith("_id")]
    idish.sort(key=lambda n: 0 if (params.get(n) or {}).get("in") == "path" else 1)
    return idish


async def _execute_plan(db: AsyncSession, plan: ExecutionPlan, trace: Trace, steps: list[PlanStep]) -> dict:
    """The real CaMeL chain at runtime:
      query → executor.read (real biz_records, owner-scoped)
      parse → Q-LLM over the *fetched data slice* (output stays `parsed`)
      write → executor.execute with args resolved from prior outputs + injected scope
    """
    rows: list[dict] = []        # accumulated query data (capability: data)
    selected: list[str] = []     # Q-LLM parsed selection (capability: parsed)
    step_rows: dict[int, list[dict]] = {}   # per-step query output, for $stepN refs
    query_errors: list[str] = []            # error codes from failed reads (for honest replies)
    total_hint: int | None = None           # paginated grand-total (for "how many" answers)

    for st in steps:
        if st.kind == "query" and st.op_key:
            ex = await _op_executor(db, trace.tenant_id, st.op_key)
            meta: dict = {}
            fetched = await ex.read(db, trace.tenant_id, st.op_key,
                                    _resolve_refs(dict(st.input_refs_json or {}), step_rows), meta)
            if meta.get("total") is not None:
                total_hint = meta["total"]
            # distinguish real rows from an executor error envelope ([{'error':..}])
            err = fetched[0].get("error") if (len(fetched) == 1 and isinstance(fetched[0], dict)
                                              and set(fetched[0]) == {"error"}) else None
            real = [] if err else fetched
            rows.extend(real)
            step_rows[st.step_no] = real
            if err:
                query_errors.append(err)
            st.status = "error" if err else "done"
            await audit.append_event(db, plan.trace_id, "DATA_READ",
                                     {"op": st.op_key, "rows": len(real),
                                      "error": err}, cap="data")

        elif st.kind == "parse":
            # Q-LLM is actually invoked here, on quarantined data only
            parsed = await qparser.parse(db, plan.trace_id, tenant_id=trace.tenant_id,
                                          instruction=st.label, data_slice=rows)
            # Q-LLM's typed selection is authoritative; no domain-specific fallback
            ids = parsed.get("selected_ids") or []
            selected = [str(i) for i in ids if i not in (None, "")]
            st.status = "done"
            await audit.append_event(db, plan.trace_id, "QLLM_PARSED",
                                     {"selected": len(selected), "capability": "parsed"}, cap="parsed")

        elif st.kind == "write" and st.op_key:
            idem = f"{plan.id}:{st.step_no}"
            existing = (
                await db.execute(select(Execution).where(Execution.idempotency_key == idem))
            ).scalar_one_or_none()
            if existing is not None:
                st.status = "done" if existing.status == "ok" else "error"
                continue
            # Resolve args: (1) planner-emitted $stepN.field references from prior
            # query outputs, (2) a chained record id into declared id-like params
            # the planner left unset — all fully target-agnostic.
            kwargs = _resolve_refs(dict(st.input_refs_json or {}), step_rows)
            op = await _load_op(db, trace.tenant_id, st.op_key)
            chained = (selected[0] if selected else None) or (_row_id(rows[0]) if rows else None)
            if chained is not None:
                for pname in _id_params(op) or ["id"]:
                    kwargs.setdefault(pname, chained)
            kwargs.pop("user_id", None)  # not an executor arg; scope already applied at read
            st.input_refs_json = kwargs  # persist the resolved args
            ex = get_executor(op.executor_binding if op else None)
            started = datetime.now(timezone.utc)
            res = await ex.execute(db, trace.tenant_id, st.op_key, kwargs)
            latency = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            db.add(Execution(
                trace_id=plan.trace_id, plan_step_id=st.id, op_key=st.op_key,
                executor=ex.name, status="error" if res.error_code else "ok",
                before_state=res.before_state, after_state=res.after_state,
                idempotency_key=idem, latency_ms=latency,
                error_code=(res.error_code or "")[:60] or None,  # column is String(60)
            ))
            st.status = "done" if not res.error_code else "error"
            await audit.append_event(db, plan.trace_id, "OPERATION_EXECUTED",
                                     {"op": st.op_key, "executor": ex.name, "latency_ms": latency,
                                      "target": chained, "error": res.error_code}, cap="write")
        else:
            st.status = "done"

    return {"rows": rows, "selected": selected, "query_errors": query_errors,
            "total_hint": total_hint}
