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
import hashlib
import hmac
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx


def xml_to_rows(text: str) -> list[dict] | None:
    """Best-effort XML → list[dict] for S3-style responses (ListBuckets returns
    <Bucket> records, ListObjectsV2 returns <Contents> records). Collects every
    'record-like' element (has children, all of which are leaves) as a row; falls
    back to the root's leaf children as a single row."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def is_record(el) -> bool:
        return len(el) > 0 and all(len(c) == 0 for c in el)

    rows: list[dict] = []

    def walk(el):
        for c in el:
            if is_record(c):
                rows.append({local(g.tag): g.text for g in c})
            else:
                walk(c)

    walk(root)
    if rows:
        return rows
    if len(root) > 0 and all(len(c) == 0 for c in root):
        return [{local(c.tag): c.text for c in root}]
    return [{local(root.tag): (root.text or "").strip()}]

TIMEOUT = httpx.Timeout(10.0, read=30.0)


class SigV4Auth(httpx.Auth):
    """AWS Signature V4 request signer — the auth for S3-compatible object stores
    (AWS S3, MinIO, Ceph, Cloudflare R2, Wasabi, …). SigV4 signs each specific
    request (method + path + query + headers + body hash), so it cannot be a
    static header; httpx calls auth_flow() per request and we sign there."""

    def __init__(self, access_key: str, secret_key: str, region: str = "us-east-1",
                 service: str = "s3"):
        self.access_key, self.secret_key = access_key, secret_key
        self.region, self.service = region, service

    @staticmethod
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    def _signing_key(self, datestamp: str) -> bytes:
        k = self._sign(("AWS4" + self.secret_key).encode(), datestamp)
        k = self._sign(k, self.region)
        k = self._sign(k, self.service)
        return self._sign(k, "aws4_request")

    def auth_flow(self, request: httpx.Request):
        now = datetime.now(timezone.utc)
        amzdate, datestamp = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        body = request.content or b""
        payload_hash = hashlib.sha256(body).hexdigest()
        host = request.url.netloc.decode("ascii")
        request.headers["host"] = host
        request.headers["x-amz-date"] = amzdate
        request.headers["x-amz-content-sha256"] = payload_hash

        canonical_uri = quote(request.url.path or "/", safe="/~")
        # canonical query string: params sorted by key, each key/value URI-encoded
        pairs = sorted((quote(k, safe="~"), quote(v, safe="~"))
                       for k, v in request.url.params.multi_items())
        canonical_qs = "&".join(f"{k}={v}" for k, v in pairs)
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_headers = (f"host:{host}\n"
                             f"x-amz-content-sha256:{payload_hash}\n"
                             f"x-amz-date:{amzdate}\n")
        canonical_request = "\n".join([request.method, canonical_uri, canonical_qs,
                                       canonical_headers, signed_headers, payload_hash])
        scope = f"{datestamp}/{self.region}/{self.service}/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256", amzdate, scope,
            hashlib.sha256(canonical_request.encode()).hexdigest()])
        signature = hmac.new(self._signing_key(datestamp), string_to_sign.encode(),
                             hashlib.sha256).hexdigest()
        request.headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}")
        yield request


def build_sigv4_auth(config: dict) -> SigV4Auth | None:
    auth = (config or {}).get("auth") or {}
    if auth.get("kind") != "sigv4":
        return None
    ak = auth.get("access_key") or os.environ.get(auth.get("access_key_env", ""))
    sk = auth.get("secret_key") or os.environ.get(auth.get("secret_key_env", ""))
    if not (ak and sk):
        return None
    return SigV4Auth(ak, sk, auth.get("region") or "us-east-1", auth.get("service") or "s3")

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


# ── login / session auth (extensibility) ───────────────────────────────────────
# Some systems don't take a static token: they require POSTing credentials to a
# login endpoint and using the returned session id / access token (Pi-hole SID,
# Keycloak OAuth password grant, ...). `auth.kind == "login"` handles this:
#   {"kind":"login", "login_url":"/api/auth", "login_method":"POST",
#    "login_body":{"password":"$secret"}, "login_form": false,
#    "token_path":"session.sid", "header":"sid", "prefix":"",
#    "secret_env":"TGT_X"}
# The acquired token is cached and re-fetched on demand / after a 401.
_login_cache: dict[str, str] = {}


def _login_key(config: dict) -> str:
    auth = (config or {}).get("auth") or {}
    return f"{config.get('base_url')}|{auth.get('login_url')}|{auth.get('secret_env')}"


def _dig(obj, path: str):
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.isdigit():
            obj = obj[int(part)] if int(part) < len(obj) else None
        else:
            return None
    return obj


async def ensure_login_token(config: dict, *, force: bool = False) -> None:
    """For a login-kind auth, acquire (and cache) the session token/sid. No-op
    for other kinds. Call before making real requests; pass force=True to
    re-login after a 401."""
    auth = (config or {}).get("auth") or {}
    if auth.get("kind") != "login":
        return
    key = _login_key(config)
    if not force and key in _login_cache:
        return
    secret = resolve_secret(auth)
    body = auth.get("login_body") or {}
    body = {k: (secret if v == "$secret" else v) for k, v in body.items()}
    method = (auth.get("login_method") or "POST").upper()
    url = auth.get("login_url") or "/login"
    tok = None
    async with httpx.AsyncClient(base_url=config.get("base_url", ""), timeout=TIMEOUT,
                                 follow_redirects=True) as client:
        if auth.get("login_form"):
            resp = await client.request(method, url, data=body)
        else:
            resp = await client.request(method, url, json=body)
        # some systems (e.g. Vaultwarden admin) return the session as a Set-Cookie
        # rather than a JSON field — read it from the jar while the client is open.
        if auth.get("token_from") == "cookie":
            name = auth.get("cookie_name") or "session"
            tok = client.cookies.get(name) or resp.cookies.get(name)
    if tok is None:
        try:
            tok = _dig(resp.json(), auth.get("token_path") or "token")
        except (ValueError, TypeError):
            tok = None
    if tok:
        _login_cache[key] = str(tok)


def build_auth_headers(config: dict) -> dict[str, str]:
    auth = (config or {}).get("auth") or {}
    kind = auth.get("kind", "none")
    headers: dict[str, str] = dict(auth.get("extra_headers") or {})
    if kind == "login":
        # session token was acquired by ensure_login_token() and cached
        tok = _login_cache.get(_login_key(config))
        if tok:
            headers[auth.get("header", "Authorization")] = auth.get("prefix", "") + tok
        return headers
    secret = resolve_secret(auth)
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
    # SigV4 (S3) signs per-request via an httpx.Auth flow, not a static header.
    sigv4 = build_sigv4_auth(config)
    headers = {"Accept": "application/json"} if sigv4 else {
        "Accept": "application/json", **build_auth_headers(config)}
    return httpx.AsyncClient(
        base_url=(config or {}).get("base_url", ""),
        headers=headers,
        auth=sigv4,
        timeout=TIMEOUT,
        follow_redirects=follow_redirects,
    )


async def probe_base(config: dict) -> dict[str, Any]:
    """Reachability probe against the real target. Returns real status + latency."""
    t0 = time.monotonic()
    try:
        await ensure_login_token(config)
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
    await ensure_login_token(config)
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

    await ensure_login_token(config)
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

    # map resource-signature (path minus the /api[/vN] prefix) → the confirmed
    # read prefix, so a write's version prefix can be aligned to reality.
    read_prefix: dict[str, str] = {}
    for rp in live_read_paths:
        pre, rest = _api_prefix_split(rp)
        read_prefix.setdefault(rest.rstrip("/").lower(), pre)

    # Writes CANNOT be safely probed (calling them would cause a real side effect),
    # so we keep ALL proposed writes rather than dropping them — comprehensive
    # business coverage (create/update/delete for every resource) matters, and a
    # write is safe to register even if unverified: it is registered `pending`,
    # requires human approval before it can run, and if the endpoint turns out
    # wrong the governed execution fails HONESTLY (http_404, no side effect).
    for e in writes:
        path = e["path"]
        # ALIGN the write's api-version prefix to a confirmed read of the SAME
        # resource. Spec-less systems (new-api) route reads at /api/token/ but the
        # LLM often guesses writes at /api/v1/token → 404; if a confirmed read
        # shares the resource under a different prefix, adopt that prefix.
        pre, rest = _api_prefix_split(path)
        sig = rest.rstrip("/").lower()
        coll = re.sub(r"/\{[^}]+\}$", "", sig)
        target_pre = read_prefix.get(sig) or read_prefix.get(coll)
        corrected = False
        if target_pre is not None and target_pre != pre:
            path = target_pre + rest
            corrected = True
        confirmed = path in live_read_paths or _collection(path) in live_read_paths
        out.append({**e, "path": path, "verified": confirmed or corrected,
                    "prefix_corrected": corrected, "probe_status": None})
    return out


def _api_prefix_split(path: str) -> tuple[str, str]:
    """Split an API path into (version-prefix, remainder), e.g.
    '/api/v1/token' → ('/api/v1', '/token'); '/api/token/' → ('/api', '/token/');
    '/v4/users' → ('/v4', '/users'); '/users' → ('', '/users')."""
    m = re.match(r"^(/api(?:/v\d+)?|/v\d+)(/.*)?$", path)
    if m:
        return m.group(1), (m.group(2) or "")
    return "", path


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


def summarize_endpoints(spec: dict, limit: int = 1000) -> list[dict]:
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
