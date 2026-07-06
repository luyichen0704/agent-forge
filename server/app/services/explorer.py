"""Real exploration of a data source.

Runs as a background task: streams phase/extraction events into
`exploration_events` (consumed by the Live screen over SSE).

For `api` sources with a configured `base_url` the pipeline is fully real:
  phase 1 全局认知 — HTTP reachability probe (real status/latency)
  phase 2 深度探索 — fetch + parse the target's OpenAPI/Swagger spec
  phase 3 操作生成 — P-LLM selects operations FROM THE REAL ENDPOINT LIST;
                     each operation is registered with an APIExecutor binding
                     (method/path/params) so execution hits the real system
  phase 4 能力标注 — capability tagging + registry activation

Sources without connection config fall back to metadata-only extraction
(legacy behaviour), clearly marked in the event stream.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.registry import Operation, OperationPermission
from app.models.sources import (
    DataSource, DiscoveredOperation, ExplorationEvent, ExplorationJob,
)
from app.services import targets
from app.services.llm import llm
from app.services.llm_config import resolve as resolve_profile

EXTRACT_SYSTEM = """\
You explore an enterprise data source and propose callable operations an AI agent
could expose. Return JSON:
{"entities":[{"name":..,"fields":[..]}],
 "operations":[{"key":"area.verb","kind":"query|mutation","desc":".."}],
 "rules":[".."], "chains":[".."]}
Keep it realistic and concise (3-6 operations)."""

EXTRACT_SYSTEM_API = """\
You are given the REAL endpoint catalogue of a live enterprise system.
Select the 6-10 most valuable operations to expose to a governed AI agent.
Rules:
- ONLY use endpoints from the catalogue verbatim (copy method + path exactly).
- Prefer business-level reads (lists, search, detail) and a few key writes.
- Skip auth/login/health/metrics/static endpoints.
Return COMPACT JSON (at most 4 entities with ≤6 fields each, ≤4 rules, ≤3 chains):
{"entities":[{"name":..,"fields":[..]}],
 "operations":[{"key":"area.verb","desc":"..","method":"GET","path":"/api/.."}],
 "rules":["business rules you can infer"], "chains":["likely multi-step chains"]}
Operation keys are short snake area.verb identifiers, e.g. "repo.search".
desc must be ≤15 words."""


async def _emit(db, job_id: uuid.UUID, event_type: str, payload: dict) -> None:
    # lock the job row so concurrent emits can't collide on seq (uq_expl_event_seq)
    await db.execute(select(ExplorationJob.id).where(ExplorationJob.id == job_id).with_for_update())
    seq = (
        await db.execute(
            select(func.coalesce(func.max(ExplorationEvent.seq), 0)).where(
                ExplorationEvent.job_id == job_id
            )
        )
    ).scalar_one() + 1
    db.add(ExplorationEvent(job_id=job_id, seq=seq, event_type=event_type,
                            payload_json=payload, created_at=datetime.now(timezone.utc)))
    await db.flush()


async def run_exploration(job_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        job = await db.get(ExplorationJob, job_id)
        if job is None:
            return
        source = await db.get(DataSource, job.source_id)
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)

        cfg = source.config_json or {}
        is_live = source.type == "api" and bool(cfg.get("base_url"))

        # ---- phase 1: 全局认知 — real reachability probe ----
        job.phase, job.progress = 1, 10
        await _emit(db, job_id, "phase", {"phase": 1, "label": "全局认知"})
        await db.commit()
        endpoints: list[dict] = []
        spec_url = None
        if is_live:
            probe = await targets.probe_base(cfg)
            await _emit(db, job_id, "probe", probe)
            if not probe.get("ok"):
                await _emit(db, job_id, "error", {"error": f"target unreachable: {probe.get('error')}"})
                job.status = "error"
                source.status = "error"
                await db.commit()
                return
            await db.commit()

        # ---- phase 2: 深度探索 — real spec discovery ----
        job.phase, job.progress = 2, 35
        await _emit(db, job_id, "phase", {"phase": 2, "label": "深度探索"})
        await db.commit()
        if is_live:
            spec_url, spec = await targets.discover_spec(cfg)
            if spec is not None:
                endpoints = targets.summarize_endpoints(spec)
            # admin-supplied catalogue (config_json.endpoints) is always honoured —
            # the escape hatch for real systems that serve no machine-readable spec
            manual = targets.normalize_manual(cfg.get("endpoints") or [])
            seen = {(e["method"], e["path"]) for e in endpoints}
            endpoints += [e for e in manual if (e["method"], e["path"]) not in seen]
            mode = "openapi" if spec is not None else ("manual" if manual else "no-spec")
            await _emit(db, job_id, "spec", {
                "spec_url": spec_url, "endpoints": len(endpoints), "manual": len(manual),
                "mode": mode,
            })
            await db.commit()

        # ---- phase 3: 操作生成 — LLM over REAL endpoints (any failure must not leave job 'running') ----
        try:
            prof = await resolve_profile(db, source.tenant_id, "pllm")
            if endpoints:
                args = (prof.model, EXTRACT_SYSTEM_API,
                        f"System: {source.name} ({source.conn})\n"
                        f"Endpoint catalogue ({len(endpoints)} real endpoints):\n"
                        + targets.endpoint_digest(endpoints))
                kw = {"temperature": prof.temperature, "max_tokens": 2800}
            else:
                args = (prof.model, EXTRACT_SYSTEM,
                        f"Source type: {source.type}\nConnector: {source.connector_kind}\n"
                        f"Connection: {source.conn}\nName: {source.name}")
                kw = {"temperature": prof.temperature, "max_tokens": 900}
            try:
                data, _ = await llm.structured(*args, **kw)
            except Exception:  # noqa: BLE001 — one retry for transient gateway/JSON issues
                await _emit(db, job_id, "retry", {"stage": "extract"})
                await db.commit()
                data, _ = await llm.structured(*args, **kw)
        except Exception as exc:  # noqa: BLE001 — surface any error to the job
            await _emit(db, job_id, "error", {"error": f"{type(exc).__name__}: {exc}"})
            job.status = "error"
            source.status = "error"
            await db.commit()
            return

        job.phase = 3
        job.progress = 70
        by_binding = {(e["method"], e["path"]): e for e in endpoints}
        registered = 0
        for op in data.get("operations", [])[:10]:
            key = str(op.get("key", "")).strip()
            if not key:
                continue
            binding = None
            input_schema: dict = {}
            if endpoints:
                ep = by_binding.get((str(op.get("method", "")).upper(), op.get("path", "")))
                if ep is None:
                    # LLM proposed an endpoint not in the real catalogue — drop it
                    await _emit(db, job_id, "op_rejected", {
                        "key": key, "reason": "not in real endpoint catalogue",
                        "method": op.get("method"), "path": op.get("path"),
                    })
                    continue
                kind = "query" if ep["method"] in ("GET", "HEAD") else "mutation"
                binding = {
                    "source_id": str(source.id), "method": ep["method"], "path": ep["path"],
                    "params": ep.get("params") or {}, "body_fields": ep.get("body_fields") or [],
                }
                input_schema = {"desc": str(op.get("desc", ""))[:200],
                                "params": ep.get("params") or {},
                                "body_fields": ep.get("body_fields") or []}
                executor = "APIExecutor"
            else:
                kind = op.get("kind") if op.get("kind") in ("query", "mutation") else "query"
                executor = "FunctionExecutor"
                input_schema = {"desc": str(op.get("desc", ""))[:200]}
            db.add(DiscoveredOperation(job_id=job_id, key=key, kind=kind,
                                       input_schema=input_schema, output_schema={},
                                       capability_requirements={}, executor_hint=executor))
            await _emit(db, job_id, "op", {"key": key, "kind": kind, "desc": op.get("desc", ""),
                                           "binding": {k: binding[k] for k in ("method", "path")} if binding else None})
            await _register_operation(db, source.tenant_id, key, kind, job_id,
                                      executor=executor, binding=binding, input_schema=input_schema)
            registered += 1
            await db.commit()
            await asyncio.sleep(0.15)

        for rule in data.get("rules", [])[:4]:
            await _emit(db, job_id, "rule", {"text": rule})
        await db.commit()

        # ---- phase 4: 能力标注 ----
        job.phase = 4
        job.progress = 100
        job.status = "done"
        job.finished_at = datetime.now(timezone.utc)
        source.status = "connected"
        await _emit(db, job_id, "done", {"operations": registered,
                                         "live": bool(endpoints), "spec_url": spec_url})
        await db.commit()


async def _register_operation(db, tenant_id, key, kind, job_id, *,
                              executor: str = "FunctionExecutor",
                              binding: dict | None = None,
                              input_schema: dict | None = None) -> None:
    existing = (
        await db.execute(
            select(Operation).where(Operation.tenant_id == tenant_id, Operation.op_key == key)
        )
    ).scalar_one_or_none()
    if existing:
        # re-exploration refreshes the real-call binding (target may have moved)
        if binding and existing.binding_json != binding:
            existing.binding_json = binding
            existing.executor_binding = executor
        return
    confirm = "confirm" if kind == "mutation" else "auto"
    status = "pending" if kind == "mutation" else "active"
    op = Operation(tenant_id=tenant_id, op_key=key, version=1, kind=kind, confirm_level=confirm,
                   risk_level="high" if kind == "mutation" else "low", status=status,
                   input_schema_json=input_schema or {},
                   executor_binding=executor, rollback_binding=executor,
                   binding_json=binding,
                   policy_ref=f"{key.replace('.', '_')}_policy", created_from_job_id=job_id,
                   published_at=datetime.now(timezone.utc) if status == "active" else None)
    db.add(op)
    await db.flush()
    # default grants: employees + admins; reads also to customers (scoped self)
    grants = [("employee", None), ("admin", None)]
    if kind == "query":
        grants.append(("customer", "self"))
    for role, scope in grants:
        db.add(OperationPermission(operation_id=op.id, subject_type="role", subject_id=role,
                                   effect="allow", condition_json={"scope": scope} if scope else {}))
