"""Executor abstraction + registry.

`operations.executor_binding` names one of these. Every execution records real
before/after state into `executions`, supports idempotency, and exposes a
compensation (`rollback`) — there is no mock toast path.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
import xmlrpc.client
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import BizRecord
from app.services import targets
from app.services import xmlrpc_disco


def _truncate(payload: Any, limit: int = 4000) -> Any:
    """Cap stored response payloads so audit rows stay bounded."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return payload
    return {"_truncated": True, "preview": text[:limit]}


_ENVELOPE_KEYS = ("items", "data", "results", "records", "list", "rows", "value")


def api_body_error(payload: Any) -> str | None:
    """Detect a body-level failure on an HTTP 200 response. Many enterprise APIs
    (Go/PHP: new-api, WordPress, ...) return 200 with {"success":false,...} or an
    error envelope on failure — trusting the HTTP status alone would report a
    failed write as success. Returns a short error message if the body signals
    failure, else None. Conservative: only explicit failure flags count."""
    if not isinstance(payload, dict):
        return None
    def msg(default: str) -> str:
        for k in ("message", "msg", "error", "detail", "error_description"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                return v[:200]
        return default
    if payload.get("success") is False or payload.get("ok") is False:
        return msg("api reported success=false")
    err = payload.get("error")
    if err and not isinstance(err, bool) and "data" not in payload and "items" not in payload:
        # {"error": "..."} or {"error": {...}} with no data payload
        if isinstance(err, str) and err.strip():
            return err[:200]
        if isinstance(err, dict) and err:
            return str(err.get("message") or err.get("code") or "api error")[:200]
    errno = payload.get("errno")
    if isinstance(errno, int) and errno != 0:
        return msg(f"errno={errno}")
    return None


def _coerce(value: Any, declared_type: str | None) -> Any:
    """Best-effort coerce a value to the parameter's declared JSON type so a
    string like "3" reaches an []int/int field as the right type. Target-agnostic."""
    if declared_type in (None, "string") or not isinstance(value, str):
        return value
    try:
        if declared_type == "integer":
            return int(value)
        if declared_type == "number":
            return float(value)
        if declared_type == "boolean":
            return value.strip().lower() in ("true", "1", "yes")
        if declared_type == "array":
            inner = value.strip()
            if inner.startswith("["):
                import json as _json
                return _json.loads(inner)
            parts = [p.strip() for p in inner.split(",") if p.strip()]
            return [int(p) if p.lstrip("-").isdigit() else p for p in parts]
    except (ValueError, TypeError):
        return value
    return value


def _rows(payload: Any, _depth: int = 0) -> list[dict]:
    """Normalize an arbitrary JSON API response into list[dict] rows.

    Handles common envelopes across systems: a list of rows, a `{items:[...]}`
    style wrapper, or a `{data:{...}}` single-object wrapper (unwrapped one level
    so domain-facing previews show business fields, not the transport envelope)."""
    if isinstance(payload, list):
        return [x if isinstance(x, dict) else {"value": x} for x in payload[:200]]
    if isinstance(payload, dict):
        for key in _ENVELOPE_KEYS:
            v = payload.get(key)
            if isinstance(v, list):
                return [x if isinstance(x, dict) else {"value": x} for x in v[:200]]
        # single-object envelope (e.g. {data:{...},success:true}) → unwrap once
        if _depth == 0:
            for key in ("data", "result", "record"):
                v = payload.get(key)
                if isinstance(v, dict):
                    return _rows(v, _depth + 1)
        # map/group response (e.g. {"1":[...],"37":[...]} model groups): flatten
        # all list values into rows so the count/preview is meaningful
        vals = list(payload.values())
        if vals and all(isinstance(v, list) for v in vals):
            out: list[dict] = []
            for group, items in payload.items():
                for x in items:
                    out.append(x if isinstance(x, dict) else {"group": group, "value": x})
            return out[:200]
        return [payload]
    return [{"value": payload}]


@dataclass
class ExecutorResult:
    before_state: dict = field(default_factory=dict)
    after_state: dict = field(default_factory=dict)
    error_code: str | None = None


class Executor(ABC):
    name: str

    @abstractmethod
    async def execute(self, db: AsyncSession, tenant_id: uuid.UUID, op_key: str,
                      kwargs: dict[str, Any]) -> ExecutorResult: ...

    async def read(self, db: AsyncSession, tenant_id: uuid.UUID, op_key: str,
                   kwargs: dict[str, Any], meta_out: dict | None = None) -> list[dict]:
        """Query-step data fetch (no side effects). Default: nothing.
        meta_out (optional) may receive pagination info like {'total': N}."""
        return []

    async def rollback(self, db: AsyncSession, before_state: dict, after_state: dict) -> dict:
        """Compensate by restoring the captured before_state. Override for ops
        whose side effects are not directly reversible."""
        return before_state


async def _record(db: AsyncSession, tenant_id: uuid.UUID, kind: str, key: str) -> BizRecord | None:
    return (
        await db.execute(
            select(BizRecord).where(
                BizRecord.tenant_id == tenant_id, BizRecord.kind == kind, BizRecord.key == key
            )
        )
    ).scalar_one_or_none()


class FunctionExecutor(Executor):
    """Runs registered Python handlers against the real biz_records store."""
    name = "FunctionExecutor"

    async def read(self, db, tenant_id, op_key, kwargs, meta_out=None):
        # owner scoping: when policy injected a user_id (customer self-scope), filter to it
        owner = kwargs.get("user_id")
        kind = {"customer.query": "customer", "order.query": "order",
                "refund.query": "refund"}.get(op_key)
        if kind is None:
            # not a built-in demo op and no real API binding → NOT connected.
            # Signal an error envelope (never masquerade as "no data").
            return [{"error": "not_connected"}]
        q = select(BizRecord).where(BizRecord.tenant_id == tenant_id, BizRecord.kind == kind)
        if owner:
            try:
                q = q.where(BizRecord.owner_user_id == uuid.UUID(str(owner)))
            except (ValueError, AttributeError):
                pass
        rows = (await db.execute(q)).scalars().all()
        out = []
        for r in rows:
            item = {"key": r.key, **(r.state_json or {})}
            out.append(item)
        return out

    async def execute(self, db, tenant_id, op_key, kwargs):
        if op_key == "refund.expedite":
            key = str(kwargs.get("order_id") or kwargs.get("refund_id") or kwargs.get("id") or "")
            rec = await _record(db, tenant_id, "refund", key)
            if rec is None:
                return ExecutorResult(error_code="not_found")
            before = dict(rec.state_json)
            after = {**before, "refund_status": "expedited"}
            rec.state_json = after
            await db.flush()
            return ExecutorResult(before_state=before, after_state=after)

        if op_key == "order.cancel":
            key = str(kwargs.get("order_id") or kwargs.get("id") or "")
            rec = await _record(db, tenant_id, "order", key)
            if rec is None:
                return ExecutorResult(error_code="not_found")
            before = dict(rec.state_json)
            after = {**before, "status": "cancelled"}
            rec.state_json = after
            await db.flush()
            return ExecutorResult(before_state=before, after_state=after)

        # unknown op with no real binding → honest failure, NEVER a fake success
        # (a metadata-only stub must not report a write it did not perform)
        return ExecutorResult(error_code="not_connected")

    async def rollback(self, db, before_state, after_state):
        # restore by op kind inferred from keys present
        return before_state


class APIExecutor(Executor):
    """Calls the real external HTTP API bound to the operation.

    Binding lives in `operations.binding_json` ({source_id, method, path,
    params, body_fields}); connection + auth come from the DataSource's
    `config_json` (secrets resolved from process env — see services/targets).
    A missing binding is an explicit error, never a silent fallback.
    """
    name = "APIExecutor"

    async def _resolve(self, db, tenant_id, op_key):
        from app.models.registry import Operation
        from app.models.sources import DataSource

        op = (
            await db.execute(
                select(Operation)
                .where(Operation.tenant_id == tenant_id, Operation.op_key == op_key)
                .order_by(Operation.version.desc())
            )
        ).scalars().first()
        binding = (op.binding_json or {}) if op else {}
        if not binding.get("path"):
            return None, None
        source = await db.get(DataSource, uuid.UUID(binding["source_id"]))
        return binding, (source.config_json or {}) if source else None

    @staticmethod
    def _fill_path(path: str, kwargs: dict) -> tuple[str | None, set[str], str | None]:
        """Substitute {param} segments from kwargs. Returns (path, used, missing)."""
        used: set[str] = set()
        for name in re.findall(r"\{([^{}]+)\}", path):
            # tolerate aliases: {id} matches kwargs id / <anything>_id
            value = kwargs.get(name)
            if value is None and name == "id":
                value = next((v for k, v in kwargs.items() if k.endswith("_id")), None)
            if value is None:
                return None, used, name
            path = path.replace("{" + name + "}", str(value))
            used.add(name)
        return path, used, None

    async def _call(self, db, tenant_id, op_key, kwargs) -> tuple[Any, ExecutorResult]:
        binding, config = await self._resolve(db, tenant_id, op_key)
        if binding is None or config is None:
            return None, ExecutorResult(error_code="no_binding")
        path, used, missing = self._fill_path(binding["path"], dict(kwargs))
        if missing:
            return None, ExecutorResult(error_code=f"missing_param:{missing}")
        method = binding.get("method", "GET").upper()
        params_spec = binding.get("params") or {}
        rest = {k: _coerce(v, params_spec.get(k, {}).get("type"))
                for k, v in kwargs.items()
                if k not in used and v is not None and k != "user_id"}
        body_fields = binding.get("body_fields") or []
        body = {k: v for k, v in rest.items() if not body_fields or k in body_fields}
        query = {k: v for k, v in rest.items() if k not in body} if method not in ("GET", "DELETE") else rest

        async def _do(client, p):
            if method in ("GET", "DELETE"):
                return await client.request(method, p, params=rest)
            return await client.request(method, p, json=body, params=query or None)

        try:
            await targets.ensure_login_token(config)   # login-kind: acquire session
            async with targets.client_for(config) as client:
                resp = await _do(client, path)
                # 307/308 PRESERVE method+body (unlike 301/302) — follow them once.
                # Common for frameworks (Gin/new-api) that redirect a collection
                # POST without a trailing slash to the canonical /collection/ form.
                if resp.status_code in (307, 308):
                    loc = resp.headers.get("location")
                    if loc:
                        target = loc if loc.startswith("http") else loc
                        resp = await _do(client, target)
            # a session token expired (401) → re-login once and retry
            if resp.status_code == 401 and (config.get("auth") or {}).get("kind") == "login":
                await targets.ensure_login_token(config, force=True)
                async with targets.client_for(config) as client:
                    resp = await _do(client, path)
        except httpx.HTTPError as exc:
            return None, ExecutorResult(error_code=f"network_error:{type(exc).__name__}")
        try:
            payload: Any = resp.json()
        except ValueError:
            txt = resp.text
            # S3-compatible stores (MinIO/AWS/Ceph) answer in XML, not JSON —
            # parse it into rows so object-storage reads look like any other query.
            if txt.lstrip()[:5].lower().startswith("<?xml") or "xml" in resp.headers.get("content-type", ""):
                payload = targets.xml_to_rows(txt) or txt[:2000]
            else:
                payload = txt[:2000]
        # a data API returning 3xx (redirect to login/HTML) or >=400 is a failure,
        # never a success — do not let a followed redirect mask it (client does not
        # follow redirects; 3xx is surfaced explicitly). ALSO: many APIs return
        # HTTP 200 with a body-level failure flag ({"success":false,...}) — that is
        # a failure too, or a write would be falsely reported as done.
        if resp.status_code >= 300:
            error_code = f"http_{resp.status_code}"
        else:
            body_err = api_body_error(payload)
            # error_code is stored in a String(60) column — cap it so a long
            # upstream message can never overflow the DB and break honest failure.
            error_code = f"api_error:{body_err}"[:60] if body_err else None
        result = ExecutorResult(
            before_state={},
            after_state={"http_status": resp.status_code, "method": method, "path": path,
                         "response": _truncate(payload)},
            error_code=error_code,
        )
        return payload, result

    async def read(self, db, tenant_id, op_key, kwargs, meta_out=None):
        payload, result = await self._call(db, tenant_id, op_key, kwargs)
        if result.error_code or payload is None:
            return [{"error": result.error_code}] if result.error_code else []
        rows = _rows(payload)
        # surface the paginated grand-total so "how many" answers aren't the page size
        if meta_out is not None and isinstance(payload, dict):
            for tk in ("total", "count", "total_count", "totalCount", "totalItems"):
                v = payload.get(tk)
                if isinstance(v, int) and v > len(rows):
                    meta_out["total"] = v
                    break
        return rows

    async def execute(self, db, tenant_id, op_key, kwargs):
        _, result = await self._call(db, tenant_id, op_key, kwargs)
        return result

    async def rollback(self, db, before_state, after_state):
        # external side effects are not auto-reversible; surface the captured states
        return {"note": "external API effect — manual compensation may be required",
                "before": before_state}


def _gql_coerce(value: Any, gql_type: str) -> Any:
    """Coerce a flat kwarg to the JSON its GraphQL variable type expects."""
    base = (gql_type or "").strip("[]!").strip()
    if base in ("Int", "ID") or base == "Long":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if base == "Float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if base == "Boolean":
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        return bool(value)
    return value


class GraphQLExecutor(Executor):
    """Executes an operation bound to a GraphQL root field (query or mutation).

    Binding (operations.binding_json): {source_id, transport:"graphql",
    graphql_url, gql_type, field, selection, arg_types}. The document is built at
    call time from the field + whichever declared args the caller supplied — a
    scalar selection set gives a flat row. Auth/connection reuse the same
    DataSource config path as REST (services/targets). GraphQL `errors` are an
    honest failure, never masked.
    """
    name = "GraphQLExecutor"

    async def _resolve(self, db, tenant_id, op_key):
        from app.models.registry import Operation
        from app.models.sources import DataSource
        op = (
            await db.execute(
                select(Operation)
                .where(Operation.tenant_id == tenant_id, Operation.op_key == op_key)
                .order_by(Operation.version.desc())
            )
        ).scalars().first()
        binding = (op.binding_json or {}) if op else {}
        if not binding.get("field"):
            return None, None
        source = await db.get(DataSource, uuid.UUID(binding["source_id"]))
        return binding, (source.config_json or {}) if source else None

    @staticmethod
    def _build_document(binding: dict, kwargs: dict) -> tuple[str, dict]:
        field = binding["field"]
        gql_type = binding.get("gql_type", "query")
        arg_types = binding.get("arg_types") or {}
        selection = binding.get("selection") or ""
        used = {k: _gql_coerce(v, arg_types[k])
                for k, v in kwargs.items()
                if k in arg_types and v is not None and k != "user_id"}
        # Relay connections REQUIRE a first/last pagination arg or the server errors
        # out ("provide a first or last value"). A domain expert asking "list X" has
        # no idea about pagination, so default first:50 when the query is a connection
        # (selection has edges) and no page arg was given — makes "list" queries work.
        if ("edges" in selection and "first" in arg_types
                and "first" not in used and "last" not in used):
            used["first"] = 50
        var_decls = ", ".join(f"${k}: {arg_types[k]}" for k in used)
        arg_uses = ", ".join(f"{k}: ${k}" for k in used)
        head = gql_type + (f"({var_decls})" if var_decls else "")
        call = field + (f"({arg_uses})" if arg_uses else "")
        body = f" {{ {selection} }}" if selection else ""
        return f"{head} {{ {call}{body} }}", used

    async def _call(self, db, tenant_id, op_key, kwargs) -> tuple[Any, ExecutorResult]:
        binding, config = await self._resolve(db, tenant_id, op_key)
        if binding is None or config is None:
            return None, ExecutorResult(error_code="no_binding")
        document, variables = self._build_document(binding, dict(kwargs))
        url = binding.get("graphql_url") or config.get("graphql_url") or "/graphql"
        try:
            await targets.ensure_login_token(config)
            async with targets.client_for(config) as client:
                resp = await client.post(url, json={"query": document, "variables": variables})
            if resp.status_code == 401 and (config.get("auth") or {}).get("kind") == "login":
                await targets.ensure_login_token(config, force=True)
                async with targets.client_for(config) as client:
                    resp = await client.post(url, json={"query": document, "variables": variables})
        except httpx.HTTPError as exc:
            return None, ExecutorResult(error_code=f"network_error:{type(exc).__name__}")
        try:
            payload: Any = resp.json()
        except ValueError:
            payload = resp.text[:2000]
        error_code = None
        if resp.status_code >= 300:
            error_code = f"http_{resp.status_code}"
        elif isinstance(payload, dict) and payload.get("errors"):
            err = payload["errors"][0]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            error_code = f"graphql_error:{msg}"[:60]
        result = ExecutorResult(
            before_state={},
            after_state={"graphql_url": url, "field": binding.get("field"),
                         "response": _truncate(payload)},
            error_code=error_code,
        )
        return payload, result

    @staticmethod
    def _field_value(payload: Any, field: str) -> Any:
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                return data.get(field)
        return None

    async def read(self, db, tenant_id, op_key, kwargs, meta_out=None):
        payload, result = await self._call(db, tenant_id, op_key, kwargs)
        if result.error_code or payload is None:
            return [{"error": result.error_code}] if result.error_code else []
        binding, _ = await self._resolve(db, tenant_id, op_key)
        value = self._field_value(payload, (binding or {}).get("field", ""))
        if value is None:
            return []
        # Relay connection ({totalCount, edges:[{node}]}, à la Saleor/Shopify/GitHub):
        # the business rows are edges[].node — unwrap them, and surface totalCount as
        # the grand-total so "how many" answers reflect the whole set, not the page.
        if isinstance(value, dict) and isinstance(value.get("edges"), list):
            if meta_out is not None and isinstance(value.get("totalCount"), int):
                meta_out["total"] = value["totalCount"]
            nodes = [e["node"] for e in value["edges"]
                     if isinstance(e, dict) and isinstance(e.get("node"), dict)]
            return nodes
        if isinstance(value, (str, int, float, bool)):
            return [{(binding or {}).get("field", "value"): value}]
        return _rows(value)

    async def execute(self, db, tenant_id, op_key, kwargs):
        _, result = await self._call(db, tenant_id, op_key, kwargs)
        return result

    async def rollback(self, db, before_state, after_state):
        return {"note": "external GraphQL mutation — manual compensation may be required",
                "before": before_state}


_XMLRPC_UID: dict[tuple, int] = {}   # (base_url, db, user) → authenticated uid


class XMLRPCExecutor(Executor):
    """Executes an operation bound to an Odoo-style XML-RPC model+verb.

    Binding (operations.binding_json): {source_id, transport:"xmlrpc", model,
    rpc_method, op_kind, fields}. Auth is per-call (db, uid, password) — uid is
    cached per source. Reads run search_read/search_count; writes run
    create/write/unlink. xmlrpc Faults surface as honest failure, never masked.
    """
    name = "XMLRPCExecutor"
    _META_KEYS = {"limit", "offset", "order", "fields", "user_id", "domain", "ids", "id"}

    async def _resolve(self, db, tenant_id, op_key):
        from app.models.registry import Operation
        from app.models.sources import DataSource
        op = (
            await db.execute(
                select(Operation)
                .where(Operation.tenant_id == tenant_id, Operation.op_key == op_key)
                .order_by(Operation.version.desc())
            )
        ).scalars().first()
        binding = (op.binding_json or {}) if op else {}
        if not binding.get("model"):
            return None, None
        source = await db.get(DataSource, uuid.UUID(binding["source_id"]))
        return binding, (source.config_json or {}) if source else None

    @staticmethod
    def _uid(base_url: str, xr: dict, password: str) -> int | None:
        key = (base_url, xr.get("db"), xr.get("username"))
        if key not in _XMLRPC_UID:
            uid = xmlrpc_disco._authenticate(base_url, xr.get("db"), xr.get("username"), password)
            if not uid:
                return None
            _XMLRPC_UID[key] = uid
        return _XMLRPC_UID[key]

    def _domain(self, kwargs: dict) -> list:
        dom = kwargs.get("domain")
        if isinstance(dom, list):
            return dom
        return [[k, "=", v] for k, v in kwargs.items()
                if k not in self._META_KEYS and v is not None]

    async def _call(self, db, tenant_id, op_key, kwargs) -> tuple[Any, ExecutorResult]:
        binding, config = await self._resolve(db, tenant_id, op_key)
        if binding is None or config is None:
            return None, ExecutorResult(error_code="no_binding")
        xr = (config.get("xmlrpc") or {})
        base_url = config.get("base_url") or ""
        password = xmlrpc_disco.resolve_xmlrpc_password(xr)
        if not password:
            return None, ExecutorResult(error_code="no_credentials")
        model = binding["model"]
        method = binding.get("rpc_method", "search_read")

        def _work() -> Any:
            uid = self._uid(base_url, xr, password)
            if not uid:
                raise xmlrpc.client.Fault(1, "authentication failed")
            db_, pw = xr.get("db"), password
            if method == "search_read":
                return xmlrpc_disco._execute(base_url, db_, uid, pw, model, "search_read",
                    [self._domain(kwargs)],
                    {"fields": binding.get("fields") or ["id", "display_name"],
                     "limit": int(kwargs.get("limit") or 50)})
            if method == "search_count":
                return xmlrpc_disco._execute(base_url, db_, uid, pw, model, "search_count",
                                             [self._domain(kwargs)])
            if method == "create":
                vals = {k: v for k, v in kwargs.items() if k not in self._META_KEYS and v is not None}
                return xmlrpc_disco._execute(base_url, db_, uid, pw, model, "create", [vals])
            if method == "write":
                ids = kwargs.get("ids") or ([kwargs["id"]] if kwargs.get("id") is not None else [])
                vals = {k: v for k, v in kwargs.items() if k not in self._META_KEYS and v is not None}
                return xmlrpc_disco._execute(base_url, db_, uid, pw, model, "write",
                                             [[int(i) for i in ids], vals])
            if method == "unlink":
                ids = kwargs.get("ids") or ([kwargs["id"]] if kwargs.get("id") is not None else [])
                return xmlrpc_disco._execute(base_url, db_, uid, pw, model, "unlink",
                                             [[int(i) for i in ids]])
            raise xmlrpc.client.Fault(1, f"unsupported method {method}")

        try:
            payload = await asyncio.to_thread(_work)
            error_code = None
        except xmlrpc.client.Fault as fault:
            payload, error_code = None, f"rpc_error:{fault.faultString}"[:60]
        except (OSError, xmlrpc.client.ProtocolError) as exc:
            payload, error_code = None, f"network_error:{type(exc).__name__}"
        result = ExecutorResult(
            before_state={},
            after_state={"model": model, "method": method, "response": _truncate(payload)},
            error_code=error_code,
        )
        return payload, result

    async def read(self, db, tenant_id, op_key, kwargs, meta_out=None):
        payload, result = await self._call(db, tenant_id, op_key, kwargs)
        if result.error_code:
            return [{"error": result.error_code}]
        if isinstance(payload, int):                      # search_count → the total
            if meta_out is not None:
                meta_out["total"] = payload
            return [{"count": payload}]
        return _rows(payload)

    async def execute(self, db, tenant_id, op_key, kwargs):
        _, result = await self._call(db, tenant_id, op_key, kwargs)
        return result

    async def rollback(self, db, before_state, after_state):
        return {"note": "external ERP write — manual compensation may be required",
                "before": before_state}


class SQLExecutor(Executor):
    name = "SQLExecutor"

    async def execute(self, db, tenant_id, op_key, kwargs):
        return await FunctionExecutor().execute(db, tenant_id, op_key, kwargs)

    async def read(self, db, tenant_id, op_key, kwargs, meta_out=None):
        return await FunctionExecutor().read(db, tenant_id, op_key, kwargs, meta_out)


class RPAExecutor(Executor):
    name = "RPAExecutor"

    async def execute(self, db, tenant_id, op_key, kwargs):
        return ExecutorResult(error_code="executor_unavailable")


EXECUTORS: dict[str, Executor] = {
    e.name: e for e in (FunctionExecutor(), APIExecutor(), GraphQLExecutor(),
                        XMLRPCExecutor(), SQLExecutor(), RPAExecutor())
}


def get_executor(name: str | None) -> Executor:
    return EXECUTORS.get(name or "FunctionExecutor", EXECUTORS["FunctionExecutor"])
