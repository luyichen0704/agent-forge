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
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.registry import Operation, OperationPermission
from app.models.sources import (
    DataSource, DiscoveredOperation, ExplorationEvent, ExplorationJob,
)
from app.services import targets
from app.services import graphql_disco
from app.services import xmlrpc_disco
from app.services import s3_disco
from app.services import source_disco
from app.services.exploration_prompts import (
    DESCRIBE_METADATA, EXTRACT_ROUTES, NAME_ENDPOINTS, PROMPT_VERSION, PROPOSE_ENDPOINTS,
)
from app.config import settings
from app.services.llm import explorer_llm, explorer_model
from app.services.llm_config import resolve as resolve_profile

# endpoints that are not business operations — never name/register these
_JUNK_RE = re.compile(
    r"/(auth|login|logout|oauth|token/refresh|session|health|healthz|livez|readyz|"
    r"ping|metrics|version|swagger|openapi|api-docs|\.well-known|favicon|static|"
    r"assets|robots\.txt|ws|websocket|socket\.io)(/|$|\.)", re.I)


def _is_junk_endpoint(e: dict) -> bool:
    path = (e.get("path") or "").lower()
    return bool(_JUNK_RE.search(path))


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


_WRITE_VERBS = ("create", "update", "delete", "insert", "remove", "set", "add",
                "new", "edit", "patch", "upsert", "cancel", "send", "publish",
                "assign", "revoke", "disable", "enable", "reset", "import", "upload")
_READ_VERBS = ("search", "query", "find", "list", "get", "fetch", "read", "recent",
               "report", "lookup", "count", "detail", "summary", "execute", "run",
               "export", "download", "view", "stat")
_WRITE_RE = re.compile(r"\b(" + "|".join(_WRITE_VERBS) + r")\b")
_READ_RE = re.compile(r"\b(" + "|".join(_READ_VERBS) + r")\b")


def _infer_kind(method: str, *texts: str) -> str:
    """Classify an operation as query|mutation by INTENT, not just HTTP method.
    GET/HEAD are always reads. For POST/PUT (some systems, e.g. Metabase, expose
    reads as POST), downgrade to 'query' ONLY when the naming clearly signals a
    read and shows no write verb — otherwise treat as a mutation (safe default:
    writes require confirmation). Word-boundary matched so 'dataset' is not read
    as 'set'."""
    if method in ("GET", "HEAD"):
        return "query"
    if method == "DELETE":
        return "mutation"
    blob = " ".join(t.lower() for t in texts if t).replace(".", " ").replace("_", " ")
    if _WRITE_RE.search(blob):
        return "mutation"
    if _READ_RE.search(blob):
        return "query"
    return "mutation"


async def _extract_from_source(db, job_id, cfg, prof) -> list[dict] | None:
    """Discover endpoints from the target's own source code (route definitions).
    Acquires the source (local path or shallow clone), locates the route files, and
    has the LLM extract every real route (composing group prefixes). Returns a
    deduped endpoint list, or None if the source is unavailable / yields nothing."""
    src = cfg.get("source") or {}
    root = await source_disco.acquire_source(src)
    if not root:
        await _emit(db, job_id, "warn", {"stage": "source",
                                         "error": "source unavailable (clone failed or path missing)"})
        await db.commit()
        return None
    files = source_disco.find_route_files(root)
    if not files:
        await _emit(db, job_id, "warn", {"stage": "source", "error": "no route-definition files found"})
        await db.commit()
        return None
    chunks = source_disco.route_bundle(files)
    by_key: dict = {}
    for chunk in chunks:
        try:
            d, _ = await explorer_llm.structured(explorer_model(prof.model), EXTRACT_ROUTES,
                                                 chunk, temperature=prof.temperature)
            for e in targets.normalize_manual(d.get("endpoints") or []):
                by_key.setdefault((e["method"], e["path"]), e)
        except Exception:  # noqa: BLE001 — a failed chunk is not fatal; keep the rest
            continue
    eps = list(by_key.values())
    await _emit(db, job_id, "source", {"files": len(files), "chunks": len(chunks),
                                       "endpoints": len(eps),
                                       "repo": src.get("repo") or src.get("path")})
    await db.commit()
    return eps or None


def _graphql_ops_list(endpoints: list[dict]) -> list[dict]:
    """Deterministically turn discovered GraphQL fields into named operations.
    The field name is a stable identifier, so key/kind/binding need no LLM — this
    both avoids the naming model rewriting GraphQL to 'POST /graphql' and gives a
    100% reliable endpoint match. Description stays human-readable for routing."""
    ops = []
    for e in endpoints:
        field = e["path"]
        gt = e.get("gql_type", "query")
        verb = "查询" if gt == "query" else "变更"
        ret = (e.get("summary", "") or "").replace("GraphQL ", "")
        ops.append({"key": field, "method": e["method"], "path": field,
                    "kind": gt, "desc": f"{verb} {field}（{ret}）"[:200]})
    return ops


_XMLRPC_VERB_CN = {"search": "查询", "count": "统计", "create": "新建",
                   "update": "更新", "delete": "删除"}


def _xmlrpc_ops_list(endpoints: list[dict]) -> list[dict]:
    """Deterministically name Odoo XML-RPC model.verb pseudo-endpoints. model.verb
    is a stable identifier, so no LLM naming — key = model.verb, human desc from
    the model's display name + the CRUD verb."""
    ops = []
    for e in endpoints:
        verb = e["path"].rsplit(".", 1)[-1]
        kind = "query" if e.get("op_kind") == "query" else "mutation"
        model_name = (e.get("summary", "") or "").split(" · ")[0] or e.get("model", "")
        cn = _XMLRPC_VERB_CN.get(verb, verb)
        ops.append({"key": e["path"], "method": e["method"], "path": e["path"],
                    "kind": kind, "desc": f"{cn}{model_name}"[:200]})
    return ops


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
    spec_url = None
    # GraphQL transport: a single-endpoint introspectable schema. When configured,
    # it is authoritative (like OpenAPI) — no LLM guessing needed.
    if cfg.get("graphql_url"):
        gql_eps = await graphql_disco.discover_graphql(cfg)
        if gql_eps:
            await _emit(db, job_id, "graphql", {"endpoint": cfg["graphql_url"],
                                                "fields": len(gql_eps)})
            await db.commit()
            manual = targets.normalize_manual(cfg.get("endpoints") or [])
            seen = {(e["method"], e["path"]) for e in gql_eps}
            gql_eps += [e for e in manual if (e["method"], e["path"]) not in seen]
            return gql_eps, "graphql", cfg["graphql_url"]
    # XML-RPC transport (Odoo-style): uniform CRUD per model, discovered via RPC.
    if cfg.get("xmlrpc"):
        rpc_eps = await xmlrpc_disco.discover_xmlrpc(cfg)
        if rpc_eps:
            await _emit(db, job_id, "xmlrpc", {"models": len({e["model"] for e in rpc_eps}),
                                               "ops": len(rpc_eps)})
            await db.commit()
            return rpc_eps, "xmlrpc", f"{cfg.get('base_url','')}/xmlrpc/2"
    # S3 transport (SigV4 object storage): fixed CRUD + enumerated buckets. These
    # are ordinary REST endpoints (bind to APIExecutor); SigV4 signing + XML rows
    # are handled in client_for/APIExecutor, so they flow the normal naming path.
    if ((cfg.get("auth") or {}).get("kind")) == "sigv4":
        s3_eps = await s3_disco.discover_s3(cfg)
        if s3_eps:
            await _emit(db, job_id, "s3", {"buckets": len([e for e in s3_eps if e["method"] == "GET"
                                                            and e["path"] not in ("/", "/{bucket}")]),
                                           "ops": len(s3_eps)})
            await db.commit()
            return s3_eps, "s3", f"{cfg.get('base_url','')}"
    spec_url, spec = await targets.discover_spec(cfg)
    # PREFERRED when no served spec but the target is open-source: extract endpoints
    # from its OWN route definitions (ground truth) instead of guessing from the
    # product name. Still probe-verified below to catch source/instance version drift.
    src_eps = (await _extract_from_source(db, job_id, cfg, prof)
               if (spec is None and cfg.get("source")) else None)
    if spec is not None:
        endpoints = targets.summarize_endpoints(spec)
        mode = "openapi"
    elif src_eps and (verified := await targets.validate_endpoints(cfg, src_eps)):
        await _emit(db, job_id, "verify", {"proposed": len(src_eps), "verified": len(verified)})
        await db.commit()
        endpoints = verified
        mode = "source"
    else:
        # no machine-readable spec → LLM proposes, then we verify against reality.
        # MULTI-PASS: complex systems have far more endpoints than one call yields,
        # so propose repeatedly, each pass excluding what's already found, until a
        # pass adds nothing new (or a cap). Breadth is the goal — probing discards
        # any wrong guess, so more passes = more real coverage.
        base_prompt = (f"System name: {source.name}\nKind: {source.type}\n"
                       f"Connector: {source.connector_kind}\nConnection: {source.conn}\n"
                       f"Base URL: {cfg.get('base_url')}")
        # each pass targets a DIFFERENT facet of the API, then we dedup across all
        # passes and finish with a gap-filling pass — a multi-angle sweep so no
        # resource/action is missed.
        ASPECTS = [
            "Focus on READ endpoints: list / search / get-by-id / detail / stats "
            "for EVERY business resource the product manages.",
            "Focus on WRITE endpoints: create / update / delete / status-change / "
            "batch / action endpoints for EVERY business resource.",
            "Focus on ADMIN / configuration / settings / options / pricing / "
            "grouping / import-export and any less-common secondary resources.",
            "GAP-FILL: given everything already found, add every remaining endpoint "
            "you are confident exists — complete the missing CRUD verbs per resource.",
        ]
        by_key: dict = {}
        prop_err = None
        for _pass, aspect in enumerate(ASPECTS):
            extra = f"\n\nTHIS PASS — {aspect}"
            if by_key:
                already = ", ".join(sorted(f"{m} {p}" for (m, p) in list(by_key)[:200]))
                extra += ("\n\nAlready found (do NOT repeat; propose DIFFERENT, additional "
                          f"real endpoints):\n{already}")
            try:
                proposal, _ = await explorer_llm.structured(
                    explorer_model(prof.model), PROPOSE_ENDPOINTS, base_prompt + extra,
                    temperature=prof.temperature)
                new = targets.normalize_manual(proposal.get("endpoints") or [])
            except Exception as exc:  # noqa: BLE001 — a failed pass is not fatal
                prop_err = f"{type(exc).__name__}: {exc}"
                new = []
            added = 0
            for e in new:
                k = (e["method"], e["path"])
                if k not in by_key:
                    by_key[k] = e; added += 1
            await _emit(db, job_id, "propose", {"pass": _pass + 1, "aspect": aspect[:24],
                                                "added": added, "total": len(by_key)})
            await db.commit()
        if prop_err and not by_key:
            await _emit(db, job_id, "warn", {"stage": "propose", "error": prop_err[:200]})
            await db.commit()
        proposed = list(by_key.values())
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

        # ---- phase 3: 操作生成 — name EVERY real endpoint, comprehensively ----
        # Complex systems have hundreds of endpoints; a single LLM call can't name
        # them all. Chunk the verified endpoints and name the batches CONCURRENTLY
        # (bounded by the LLM client's semaphore) — like a PM fanning out to many
        # workers — so coverage scales to full-CRUD across every resource.
        job.phase, job.progress = 3, 70
        emodel = explorer_model(prof.model)
        try:
            if endpoints and mode in ("graphql", "xmlrpc"):
                # GraphQL fields / XML-RPC model.verb are machine-readable identifiers,
                # so naming is deterministic — no LLM guessing (which would rewrite them
                # and break the endpoint match). key/kind come straight from the schema.
                biz = [e for e in endpoints if not _is_junk_endpoint(e)]
                ops_list = (_graphql_ops_list(biz) if mode == "graphql"
                            else _xmlrpc_ops_list(biz))
                await _emit(db, job_id, "name", {"mode": mode, "endpoints": len(biz),
                                                 "named": len(ops_list)})
                await db.commit()
            elif endpoints:
                biz = [e for e in endpoints if not _is_junk_endpoint(e)]
                CHUNK = 40
                batches = [biz[i:i + CHUNK] for i in range(0, len(biz), CHUNK)]

                # naming is a mechanical task (assign key+desc to REAL endpoints) —
                # use the fast DeepSeek model so hundreds of endpoints stay tractable;
                # the harder recall (propose) already used the stronger model.
                name_model = settings.qllm_model or emodel

                async def _name_batch(batch: list[dict]) -> list[dict]:
                    user = (f"System: {source.name} ({source.conn})\n"
                            f"Endpoints to name ({len(batch)}):\n"
                            + targets.endpoint_digest(batch, max_chars=24000))
                    for _try in range(2):
                        try:
                            d, _ = await explorer_llm.structured(name_model, NAME_ENDPOINTS, user,
                                                                 temperature=prof.temperature)
                            return d.get("operations", [])
                        except Exception:  # noqa: BLE001 — retry the batch once
                            continue
                    return []

                results = await asyncio.gather(*[_name_batch(b) for b in batches])
                ops_list = [op for r in results for op in r]
                await _emit(db, job_id, "name", {"batches": len(batches),
                                                 "endpoints": len(biz), "named": len(ops_list)})
                await db.commit()
            else:
                d, _ = await explorer_llm.structured(
                    emodel, DESCRIBE_METADATA,
                    f"Source type: {source.type}\nConnector: {source.connector_kind}\n"
                    f"Connection: {source.conn}\nName: {source.name}",
                    temperature=prof.temperature)
                ops_list = d.get("operations", [])
        except Exception as exc:  # noqa: BLE001 — surface any error to the job
            await _emit(db, job_id, "error", {"error": f"{type(exc).__name__}: {exc}"})
            job.status = "error"
            source.status = "error"
            await db.commit()
            return

        by_binding = {(e["method"], e["path"]): e for e in endpoints}
        slug = _source_slug(source)
        registered = 0
        # re-exploration convergence: an endpoint already registered for THIS source
        # (possibly under a different op_key from an earlier run) is not registered
        # again — so re-exploring is idempotent instead of accumulating semantic
        # duplicates of the same (method, path).
        existing_ops = (
            await db.execute(select(Operation).where(Operation.source_id == source.id))
        ).scalars().all()
        seen_ep: set = set()
        for eo in existing_ops:
            b = eo.binding_json or {}
            if b.get("method") and b.get("path"):
                seen_ep.add((b["method"], b["path"]))
        for op in ops_list[:800]:
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
                ep_id = (ep["method"], ep["path"])
                if ep_id in seen_ep:
                    continue          # already registered this endpoint from another batch
                seen_ep.add(ep_id)
                if ep.get("transport") == "graphql":
                    # GraphQL field: kind comes straight from the schema (Query vs
                    # Mutation), binding carries what GraphQLExecutor needs to build
                    # the document — the field, its arg types, and a scalar selection.
                    kind = "query" if ep.get("gql_type") == "query" else "mutation"
                    binding = {
                        "source_id": str(source.id), "transport": "graphql",
                        "graphql_url": ep["graphql_url"], "gql_type": ep["gql_type"],
                        "field": ep["path"], "selection": ep.get("selection", ""),
                        "arg_types": ep.get("arg_types") or {},
                    }
                    input_schema = {"desc": str(op.get("desc", ""))[:200],
                                    "params": ep.get("params") or {}}
                    executor = "GraphQLExecutor"
                elif ep.get("transport") == "xmlrpc":
                    # Odoo XML-RPC: kind from the CRUD verb; binding carries the model,
                    # the odoo method, and a default field set for readable rows.
                    kind = "query" if ep.get("op_kind") == "query" else "mutation"
                    binding = {
                        "source_id": str(source.id), "transport": "xmlrpc",
                        "model": ep["model"], "rpc_method": ep["rpc_method"],
                        "op_kind": ep.get("op_kind", "query"), "fields": ep.get("fields") or [],
                    }
                    input_schema = {"desc": str(op.get("desc", ""))[:200],
                                    "params": ep.get("params") or {}}
                    executor = "XMLRPCExecutor"
                else:
                    kind = _infer_kind(ep["method"], raw_key, op.get("desc", ""),
                                       ep.get("path", ""), ep.get("summary", ""))
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
                                           "binding": ({"method": binding.get("method") or binding.get("gql_type") or binding.get("rpc_method"),
                                                        "path": binding.get("path") or binding.get("field") or binding.get("model")}
                                                       if binding else None)})
            await _register_operation(db, source, key, kind, job_id,
                                      executor=executor, binding=binding, input_schema=input_schema)
            registered += 1
            await db.commit()
            await asyncio.sleep(0.03)

        # ---- phase 4: 能力标注 ----
        job.phase = 4
        job.progress = 100
        job.status = "done"
        job.finished_at = datetime.now(timezone.utc)
        source.status = "connected"
        await _emit(db, job_id, "done", {"operations": registered,
                                         "live": bool(endpoints), "spec_url": spec_url})
        await db.commit()





def _source_slug(source) -> str:
    """Short stable slug identifying a source, for op-key qualification.
    Prefers the first ascii-alnum token of the name, else the base_url host,
    else a hex prefix of the source id."""
    m = re.search(r"[A-Za-z][A-Za-z0-9]{1,}", source.name or "")
    if m:
        return m.group(0).lower()
    base = (source.config_json or {}).get("base_url", "")
    host = re.sub(r"^https?://", "", base).split(":")[0].split("/")[0]
    host = re.sub(r"[^a-z0-9]", "", host.lower())
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
    method = (binding or {}).get("method", "").upper()
    risk, confirm, grants = _risk_policy(kind, key, method)
    status = "pending" if kind == "mutation" else "active"
    op = Operation(tenant_id=tenant_id, source_id=source.id, op_key=key, version=1, kind=kind,
                   confirm_level=confirm, risk_level=risk, status=status,
                   input_schema_json=input_schema or {},
                   executor_binding=executor, rollback_binding=executor,
                   binding_json=binding,
                   policy_ref=f"{key.replace('.', '_')}_policy", created_from_job_id=job_id,
                   published_at=datetime.now(timezone.utc) if status == "active" else None)
    db.add(op)
    await db.flush()
    for role, scope in grants:
        db.add(OperationPermission(operation_id=op.id, subject_type="role", subject_id=role,
                                   effect="allow", condition_json={"scope": scope} if scope else {}))


# destructive / privileged verbs → tightest governance
_DESTRUCTIVE = ("delete", "remove", "destroy", "purge", "drop", "ban", "revoke",
                "disable", "deactivate", "wipe", "reset", "cancel")
_ADMIN_AREA = ("admin", "setting", "config", "option", "policy", "permission",
               "role", "secret", "key", "credential", "billing", "quota", "channel")


def _risk_policy(kind: str, key: str, method: str) -> tuple[str, str, list]:
    """Governance for a discovered op, by risk. Returns (risk, confirm, grants).
    Reads are broadly available; writes need confirmation; destructive or
    admin/security-sensitive writes require dual approval and are admin-only."""
    k = key.lower()
    if kind != "mutation":
        # reads: everyone (customers self-scoped), auto
        return "low", "auto", [("employee", None), ("admin", None), ("customer", "self")]
    destructive = method == "DELETE" or any(w in k for w in _DESTRUCTIVE)
    sensitive = any(a in k for a in _ADMIN_AREA)
    if destructive or sensitive:
        # delete / admin / security-sensitive change → four-eyes, admins only
        return "critical", "dual", [("admin", None)]
    # ordinary create/update → single confirmation, staff + admins
    return "high", "confirm", [("employee", None), ("admin", None)]
