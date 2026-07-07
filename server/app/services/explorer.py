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
from app.services.exploration_prompts import (
    DESCRIBE_METADATA, PROMPT_VERSION, PROPOSE_ENDPOINTS, SELECT_FROM_SPEC,
)
from app.services.llm import explorer_llm, explorer_model
from app.services.llm_config import resolve as resolve_profile


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


async def _discover_endpoints(db, job_id, source, cfg, prof) -> tuple[list[dict], str, str | None]:
    """Automatic API-surface discovery for a live target. Returns
    (endpoints, mode, spec_url). Preference order:
      1. served OpenAPI/Swagger spec (authoritative)
      2. LLM proposes endpoints → PROBED against the live system, keep only real
      3. none → metadata-only extraction happens downstream
    An admin-supplied catalogue (config.endpoints) is merged as an optional
    override — it is NOT required; the framework adapts on its own.
    """
    endpoints: list[dict] = []
    spec_url, spec = await targets.discover_spec(cfg)
    if spec is not None:
        endpoints = targets.summarize_endpoints(spec)
        mode = "openapi"
    else:
        # no machine-readable spec → LLM proposes, then we verify against reality
        p_args = (explorer_model(prof.model), PROPOSE_ENDPOINTS,
                  f"System name: {source.name}\nKind: {source.type}\n"
                  f"Connector: {source.connector_kind}\nConnection: {source.conn}\n"
                  f"Base URL: {cfg.get('base_url')}")
        proposed = []
        prop_err = None
        for _try in range(2):
            try:
                # generous budget: the explorer model may be a reasoning model
                # that spends tokens before emitting the JSON answer
                proposal, _ = await explorer_llm.structured(*p_args, temperature=prof.temperature)
                proposed = targets.normalize_manual(proposal.get("endpoints") or [])
                prop_err = None
                break
            except Exception as exc:  # noqa: BLE001 — proposal failure is not fatal
                proposed = []
                prop_err = f"{type(exc).__name__}: {exc}"
        if prop_err:
            await _emit(db, job_id, "warn", {"stage": "propose", "error": prop_err[:200]})
            await db.commit()
        await _emit(db, job_id, "propose", {"proposed": len(proposed)})
        await db.commit()
        verified = await targets.validate_endpoints(cfg, proposed) if proposed else []
        await _emit(db, job_id, "verify", {"proposed": len(proposed), "verified": len(verified)})
        await db.commit()
        endpoints = verified
        mode = "probe-verified" if verified else "metadata"

    # optional admin override / augmentation
    manual = targets.normalize_manual(cfg.get("endpoints") or [])
    seen = {(e["method"], e["path"]) for e in endpoints}
    endpoints += [e for e in manual if (e["method"], e["path"]) not in seen]
    if manual and mode == "metadata":
        mode = "manual"
    return endpoints, mode, spec_url


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

        # ---- phase 2: 深度探索 — automatic API-surface discovery ----
        # (served spec → else LLM-proposes-then-probe-verifies → else metadata)
        job.phase, job.progress = 2, 35
        await _emit(db, job_id, "phase", {"phase": 2, "label": "深度探索"})
        await db.commit()
        prof = await resolve_profile(db, source.tenant_id, "pllm")
        mode = "metadata"
        if is_live:
            try:
                endpoints, mode, spec_url = await _discover_endpoints(db, job_id, source, cfg, prof)
            except Exception as exc:  # noqa: BLE001 — discovery failure is not fatal; go metadata-only
                await _emit(db, job_id, "warn", {"stage": "discovery", "error": f"{type(exc).__name__}: {exc}"})
                endpoints, mode = [], "metadata"
            await _emit(db, job_id, "spec", {
                "spec_url": spec_url, "endpoints": len(endpoints), "mode": mode,
                "prompt_version": PROMPT_VERSION,
            })
            await db.commit()

        # ---- phase 3: 操作生成 — LLM curates business ops (any failure must not leave job 'running') ----
        try:
            emodel = explorer_model(prof.model)
            if endpoints:
                args = (emodel, SELECT_FROM_SPEC,
                        f"System: {source.name} ({source.conn})\n"
                        f"Verified endpoint catalogue ({len(endpoints)} real endpoints):\n"
                        + targets.endpoint_digest(endpoints))
                kw = {"temperature": prof.temperature}
            else:
                args = (emodel, DESCRIBE_METADATA,
                        f"Source type: {source.type}\nConnector: {source.connector_kind}\n"
                        f"Connection: {source.conn}\nName: {source.name}")
                kw = {"temperature": prof.temperature}
            try:
                data, _ = await explorer_llm.structured(*args, **kw)
            except Exception:  # noqa: BLE001 — one retry for transient gateway/JSON issues
                await _emit(db, job_id, "retry", {"stage": "extract"})
                await db.commit()
                data, _ = await explorer_llm.structured(*args, **kw)
        except Exception as exc:  # noqa: BLE001 — surface any error to the job
            await _emit(db, job_id, "error", {"error": f"{type(exc).__name__}: {exc}"})
            job.status = "error"
            source.status = "error"
            await db.commit()
            return

        job.phase = 3
        job.progress = 70
        by_binding = {(e["method"], e["path"]): e for e in endpoints}
        slug = _source_slug(source)
        registered = 0
        for op in data.get("operations", [])[:10]:
            raw_key = str(op.get("key", "")).strip()
            if not raw_key:
                continue
            binding = None
            input_schema: dict = {}
            if endpoints:
                ep = by_binding.get((str(op.get("method", "")).upper(), op.get("path", "")))
                if ep is None:
                    # LLM proposed an endpoint not in the real catalogue — drop it
                    await _emit(db, job_id, "op_rejected", {
                        "key": raw_key, "reason": "not in real endpoint catalogue",
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
            # per-source op-key isolation: qualify with a source slug if this key
            # is already taken by a DIFFERENT source (avoids cross-source overwrite)
            key = await _resolve_op_key(db, source, raw_key, slug)
            db.add(DiscoveredOperation(job_id=job_id, key=key, kind=kind,
                                       input_schema=input_schema, output_schema={},
                                       capability_requirements={}, executor_hint=executor))
            await _emit(db, job_id, "op", {"key": key, "kind": kind, "desc": op.get("desc", ""),
                                           "binding": {k: binding[k] for k in ("method", "path")} if binding else None})
            await _register_operation(db, source, key, kind, job_id,
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


import re as _re


def _source_slug(source) -> str:
    """Short stable slug identifying a source, for op-key qualification.
    Prefers the first ascii-alnum token of the name, else the base_url host,
    else a hex prefix of the source id."""
    m = _re.search(r"[A-Za-z][A-Za-z0-9]{1,}", source.name or "")
    if m:
        return m.group(0).lower()
    base = (source.config_json or {}).get("base_url", "")
    host = _re.sub(r"^https?://", "", base).split(":")[0].split("/")[0]
    host = _re.sub(r"[^a-z0-9]", "", host.lower())
    return host or f"s{source.id.hex[:6]}"


async def _resolve_op_key(db, source, key: str, slug: str) -> str:
    """Return an op_key unique across sources within the tenant: the raw key if
    free or already owned by THIS source, else the key qualified by the source
    slug (and, if that still collides, by a source-id fragment)."""
    existing = (
        await db.execute(
            select(Operation).where(Operation.tenant_id == source.tenant_id, Operation.op_key == key)
        )
    ).scalar_one_or_none()
    if existing is None or existing.source_id == source.id:
        return key
    qualified = f"{slug}.{key}"
    clash = (
        await db.execute(
            select(Operation).where(Operation.tenant_id == source.tenant_id,
                                    Operation.op_key == qualified)
        )
    ).scalar_one_or_none()
    if clash is None or clash.source_id == source.id:
        return qualified
    return f"{slug}{source.id.hex[:4]}.{key}"


async def _register_operation(db, source, key, kind, job_id, *,
                              executor: str = "FunctionExecutor",
                              binding: dict | None = None,
                              input_schema: dict | None = None) -> None:
    tenant_id = source.tenant_id
    existing = (
        await db.execute(
            select(Operation).where(Operation.tenant_id == tenant_id,
                                    Operation.source_id == source.id, Operation.op_key == key)
        )
    ).scalar_one_or_none()
    if existing:
        # re-exploration refreshes the real-call binding (target may have moved)
        if binding and existing.binding_json != binding:
            existing.binding_json = binding
            existing.executor_binding = executor
        if input_schema:
            existing.input_schema_json = input_schema
        return
    confirm = "confirm" if kind == "mutation" else "auto"
    status = "pending" if kind == "mutation" else "active"
    op = Operation(tenant_id=tenant_id, source_id=source.id, op_key=key, version=1, kind=kind,
                   confirm_level=confirm,
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
