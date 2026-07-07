"""Real connectivity to external target systems.

A DataSource of type "api" carries its connection config in `config_json`:

    {
      "base_url": "http://127.0.0.1:18002",
      "openapi_url": "/swagger.v1.json",        # optional; else common paths probed
      "auth": {
        "kind": "bearer|token|basic|header|none",
        "header": "X-Api-Key",                   # kind=header only
        "prefix": "Bearer ",                     # optional custom prefix
        "username": "api",                       # kind=basic (secret is the password)
        "secret_env": "TGT_GITEA_TOKEN",          # secret resolved from process env
        "secret": "...",                         # inline fallback (tests only)
        "extra_headers": {"New-Api-User": "1"}
      }
    }

Secrets resolve at call time from the environment (`secret_env`) so they never
persist in the database or in audit payloads.
"""
from __future__ import annotations

import base64
import os
import re
import time
from typing import Any

import httpx

TIMEOUT = httpx.Timeout(10.0, read=30.0)

# Common spec locations across popular enterprise systems (Gitea, Grafana,
# NocoDB, Firefly III, WordPress, Mattermost, Metabase, Keycloak, new-api, ...)
COMMON_SPEC_PATHS = [
    "/openapi.json", "/swagger.json", "/swagger.v1.json", "/api/swagger.json",
    "/api/openapi.json", "/v3/api-docs", "/api/v1/openapi.json",
    "/api/docs/openapi.json", "/public/openapi3.json", "/api/v1/docs.json",
    "/rest/openapi.json", "/wp-json/",
]


def resolve_secret(auth: dict) -> str | None:
    env_name = auth.get("secret_env")
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return auth.get("secret")


def build_auth_headers(config: dict) -> dict[str, str]:
    auth = (config or {}).get("auth") or {}
    kind = auth.get("kind", "none")
    secret = resolve_secret(auth)
    headers: dict[str, str] = dict(auth.get("extra_headers") or {})
    if kind == "none" or secret is None:
        return headers
    if kind == "bearer":
        headers["Authorization"] = auth.get("prefix", "Bearer ") + secret
    elif kind == "token":
        headers["Authorization"] = auth.get("prefix", "token ") + secret
    elif kind == "basic":
        username = auth.get("username")
        raw = f"{username}:{secret}" if username else secret  # secret may be "user:pass"
        headers["Authorization"] = "Basic " + base64.b64encode(raw.encode()).decode()
    elif kind == "header":
        headers[auth.get("header", "Authorization")] = auth.get("prefix", "") + secret
    return headers


def client_for(config: dict, *, follow_redirects: bool = False) -> httpx.AsyncClient:
    # Always ask for JSON — some systems (e.g. Firefly III) return a 302 to an
    # HTML page on a validation error unless the request declares JSON, which
    # would mask a real failure as an HTML 200. Redirects are NOT followed for
    # executor calls: a data API returning 3xx signals a problem, not success.
    headers = {"Accept": "application/json", **build_auth_headers(config)}
    return httpx.AsyncClient(
        base_url=(config or {}).get("base_url", ""),
        headers=headers,
        timeout=TIMEOUT,
        follow_redirects=follow_redirects,
    )


async def probe_base(config: dict) -> dict[str, Any]:
    """Reachability probe against the real target. Returns real status + latency."""
    t0 = time.monotonic()
    try:
        async with client_for(config, follow_redirects=True) as client:
            resp = await client.get("/")
            return {
                "ok": True,
                "status": resp.status_code,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "server": resp.headers.get("server", ""),
            }
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }


async def discover_spec(config: dict) -> tuple[str | None, dict | None]:
    """Fetch the target's OpenAPI/Swagger spec (explicit `openapi_url` first,
    then common paths). Returns (url, parsed spec) or (None, None)."""
    candidates = []
    explicit = (config or {}).get("openapi_url")
    if explicit:
        candidates.append(explicit)
    candidates += [p for p in COMMON_SPEC_PATHS if p != explicit]
    async with client_for(config, follow_redirects=True) as client:
        for path in candidates:
            try:
                resp = await client.get(path)
                if resp.status_code != 200:
                    continue
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                continue
            if isinstance(data, dict) and ("paths" in data or "routes" in data):
                return path, data
    return None, None


async def validate_endpoints(config: dict, endpoints: list[dict],
                             max_probes: int = 150) -> list[dict]:
    """Ground LLM-proposed endpoints in the LIVE system.

    A candidate is kept only if the real target confirms the route exists:
      - GET/HEAD candidates are probed directly (fill path templates with a
        harmless placeholder); anything that is not 404/501 and not an HTML
        SPA-fallback is considered real (200/400/401/403/422 all prove the
        route is handled).
      - write candidates (POST/PUT/PATCH/DELETE) are NEVER called (that would
        cause side effects); they are accepted only if a sibling collection
        path is confirmed reachable, otherwise dropped.
    Returns the surviving endpoints, each annotated with `verified` + `probe_status`.
    """
    reads = [e for e in endpoints if e["method"] in ("GET", "HEAD")]
    writes = [e for e in endpoints if e["method"] not in ("GET", "HEAD")]
    live_read_paths: set[str] = set()   # exact template paths confirmed to exist
    out: list[dict] = []

    async with client_for(config) as client:
        for e in reads[:max_probes]:
            probe_path = re.sub(r"\{[^{}]+\}", "1", e["path"])
            try:
                resp = await client.request("GET", probe_path,
                                            params={k: 1 for k, v in e["params"].items()
                                                    if v.get("in") == "query" and v.get("required")})
            except httpx.HTTPError:
                continue
            ctype = resp.headers.get("content-type", "")
            is_spa = "text/html" in ctype  # HTML = SPA catch-all, route not really an API
            is_redirect = 300 <= resp.status_code < 400  # usually an auth/login redirect
            if resp.status_code in (404, 501) or is_spa or is_redirect:
                continue
            # 200 with a body-level failure flag (e.g. new-api /api/user/dashboard
            # → {"success":false,"message":"strconv.Atoi..."}) is a mis-bound route,
            # not a real endpoint — don't verify it.
            try:
                from app.executors.base import api_body_error
                if resp.headers.get("content-type", "").startswith("application/json") \
                        and api_body_error(resp.json()):
                    continue
            except (ValueError, ImportError):
                pass
            out.append({**e, "verified": True, "probe_status": resp.status_code})
            live_read_paths.add(e["path"])

    def _collection(path: str) -> str:
        # item routes end in a param (/users/{id}); their collection is the parent
        return path.rsplit("/", 1)[0] if path.endswith("}") else path

    for e in writes:
        # accept a write ONLY when the exact collection it targets is a confirmed
        # live read route (e.g. POST /api/v1/users ↔ GET /api/v1/users). Never call
        # the write itself — that would cause a side effect during discovery.
        if e["path"] in live_read_paths or _collection(e["path"]) in live_read_paths:
            out.append({**e, "verified": False, "probe_status": None})
    return out


def _param_entry(p: dict) -> dict:
    return {
        "in": p.get("in", "query"),
        "required": bool(p.get("required")),
        "type": (p.get("schema") or {}).get("type") or p.get("type") or "string",
        "desc": (p.get("description") or "")[:80],
    }


def _body_fields(op: dict, spec: dict) -> list[str]:
    """Top-level body property names, best-effort (OpenAPI 3 requestBody or Swagger 2 body param)."""
    schema = None
    body = op.get("requestBody")
    if isinstance(body, dict):
        content = body.get("content") or {}
        for ctype in ("application/json", "*/*"):
            if ctype in content:
                schema = content[ctype].get("schema")
                break
    else:
        for p in op.get("parameters") or []:
            if p.get("in") == "body":
                schema = p.get("schema")
                break
    if isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"].lstrip("#/").split("/")
        node: Any = spec
        for part in ref:
            node = node.get(part, {}) if isinstance(node, dict) else {}
        schema = node
    if isinstance(schema, dict):
        return list((schema.get("properties") or {}).keys())[:12]
    return []


def _spec_base_path(spec: dict) -> str:
    """API path prefix to prepend to every endpoint path.

    Swagger 2.0 puts it in `basePath` (e.g. Gitea "/api/v1"); OpenAPI 3 puts it
    in the path portion of `servers[0].url` (e.g. "/api/v3"). Dropping it makes
    every generated call hit the wrong URL (404), so it must be preserved."""
    base = spec.get("basePath")  # Swagger 2.0
    if not base:
        servers = spec.get("servers")
        if isinstance(servers, list) and servers and isinstance(servers[0], dict):
            url = str(servers[0].get("url", ""))
            # take only the path component of an absolute or relative server url
            m = re.match(r"^(?:https?://[^/]+)?(/[^?#]*)", url)
            base = m.group(1) if m else ""
    base = (base or "").rstrip("/")
    return base if base and base != "/" else ""


def summarize_endpoints(spec: dict, limit: int = 400) -> list[dict]:
    """Flatten an OpenAPI 2/3 spec (or WordPress /wp-json route map) into
    [{method, path, summary, tag, params, body_fields}]."""
    out: list[dict] = []
    base = _spec_base_path(spec)
    paths = spec.get("paths")
    if isinstance(paths, dict):  # OpenAPI 2/3
        for path, ops in paths.items():
            if not isinstance(ops, dict):
                continue
            shared = [p for p in ops.get("parameters", []) if isinstance(p, dict)]
            for method, op in ops.items():
                if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE") or not isinstance(op, dict):
                    continue
                params = {
                    p["name"]: _param_entry(p)
                    for p in shared + [q for q in op.get("parameters") or [] if isinstance(q, dict)]
                    if p.get("name") and p.get("in") in ("path", "query")
                }
                out.append({
                    "method": method.upper(),
                    "path": base + path,
                    "summary": (op.get("summary") or op.get("operationId") or op.get("description") or "")[:100],
                    "tag": (op.get("tags") or [""])[0],
                    "params": params,
                    "body_fields": _body_fields(op, spec) if method.upper() != "GET" else [],
                })
    elif isinstance(spec.get("routes"), dict):  # WordPress route map (served under /wp-json)
        wp_prefix = "/wp-json"
        for path, route in spec["routes"].items():
            if not isinstance(route, dict) or path.count("/") > 4 or "{" in path or path == "/":
                continue  # skip index + templated/namespace-root routes the LLM can't call blindly
            for ep in route.get("endpoints", []):
                for method in ep.get("methods", []):
                    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                        continue
                    args = ep.get("args") or {}
                    params = {
                        name: {"in": "query", "required": bool((a or {}).get("required")),
                               "type": (a or {}).get("type", "string") if isinstance((a or {}).get("type"), str) else "string",
                               "desc": ""}
                        for name, a in list(args.items())[:10] if isinstance(a, dict)
                    }
                    out.append({"method": method, "path": wp_prefix + path, "summary": "",
                                "tag": path.split("/")[1] if "/" in path else "",
                                "params": params if method == "GET" else {},
                                "body_fields": list(args.keys())[:12] if method != "GET" else []})
    return out[:limit]


def normalize_manual(entries: list[dict]) -> list[dict]:
    """Normalize admin-supplied endpoint catalogue (config_json.endpoints) —
    the escape hatch for real systems that don't serve an OpenAPI spec."""
    out = []
    for e in entries or []:
        method = str(e.get("method", "GET")).upper()
        path = e.get("path")
        if not path or method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            continue
        params = {}
        for name, spec in (e.get("params") or {}).items():
            if isinstance(spec, str):  # shorthand: {"q": "query"}
                spec = {"in": spec}
            params[name] = {"in": spec.get("in", "query"), "required": bool(spec.get("required")),
                            "type": spec.get("type", "string"), "desc": (spec.get("desc") or "")[:80]}
        # implicit path params from {placeholders}
        for name in re.findall(r"\{([^{}]+)\}", path):
            params.setdefault(name, {"in": "path", "required": True, "type": "string", "desc": ""})
        out.append({"method": method, "path": path, "summary": (e.get("summary") or "")[:100],
                    "tag": e.get("tag", ""), "params": params,
                    "body_fields": list(e.get("body_fields") or [])[:12]})
    return out


def endpoint_digest(endpoints: list[dict], max_chars: int = 24000) -> str:
    """Compact text catalogue of real endpoints for the P-LLM."""
    lines = []
    for e in endpoints:
        params = ",".join(
            f"{n}({v['in']}{'*' if v['required'] else ''})" for n, v in list(e["params"].items())[:8]
        )
        body = ",".join(e.get("body_fields") or [])
        line = f"{e['method']} {e['path']}"
        if e.get("summary"):
            line += f" — {e['summary']}"
        if params:
            line += f" [params: {params}]"
        if body:
            line += f" [body: {body}]"
        lines.append(line)
    text = "\n".join(lines)
    return text[:max_chars]
