"""Unit tests for real target connectivity (services/targets + APIExecutor helpers)."""
import base64

import httpx
import pytest

from app.executors.base import APIExecutor, _rows, _truncate
from app.services import targets


# ---------- auth header building ----------

def test_auth_bearer_from_env(monkeypatch):
    monkeypatch.setenv("TGT_X", "sek")
    h = targets.build_auth_headers({"auth": {"kind": "bearer", "secret_env": "TGT_X"}})
    assert h["Authorization"] == "Bearer sek"


def test_auth_token_prefix():
    h = targets.build_auth_headers({"auth": {"kind": "token", "secret": "abc"}})
    assert h["Authorization"] == "token abc"


def test_auth_basic_username_and_combined():
    h = targets.build_auth_headers({"auth": {"kind": "basic", "username": "u", "secret": "p"}})
    assert h["Authorization"] == "Basic " + base64.b64encode(b"u:p").decode()
    # WordPress-style "user:app-password" stored whole in the secret
    h2 = targets.build_auth_headers({"auth": {"kind": "basic", "secret": "u:p w x"}})
    assert h2["Authorization"] == "Basic " + base64.b64encode(b"u:p w x").decode()


def test_auth_header_kind_and_extra_headers():
    h = targets.build_auth_headers({"auth": {
        "kind": "header", "header": "X-Api-Key", "secret": "k",
        "extra_headers": {"New-Api-User": "1"},
    }})
    assert h["X-Api-Key"] == "k"
    assert h["New-Api-User"] == "1"


def test_auth_none_or_missing_secret_yields_no_auth_header():
    assert targets.build_auth_headers({}) == {}
    assert "Authorization" not in targets.build_auth_headers({"auth": {"kind": "bearer"}})


# ---------- OpenAPI summarization ----------

OPENAPI3 = {
    "openapi": "3.0.0",
    "paths": {
        "/api/v1/repos/search": {
            "get": {"summary": "Search repos", "tags": ["repository"],
                    "parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}]},
        },
        "/api/v1/repos/{owner}/{repo}/issues": {
            "parameters": [{"name": "owner", "in": "path", "required": True},
                           {"name": "repo", "in": "path", "required": True}],
            "post": {"summary": "Create issue",
                     "requestBody": {"content": {"application/json": {
                         "schema": {"properties": {"title": {}, "body": {}}}}}}},
        },
        "/metrics": {"get": {"summary": "metrics"}},
    },
}


def test_summarize_endpoints_openapi3():
    eps = targets.summarize_endpoints(OPENAPI3)
    by = {(e["method"], e["path"]): e for e in eps}
    search = by[("GET", "/api/v1/repos/search")]
    assert search["params"]["q"]["in"] == "query"
    create = by[("POST", "/api/v1/repos/{owner}/{repo}/issues")]
    assert create["params"]["owner"]["in"] == "path"
    assert create["params"]["owner"]["required"] is True
    assert "title" in create["body_fields"]


def test_summarize_endpoints_swagger2_body_ref():
    spec = {
        "swagger": "2.0",
        "definitions": {"NewOrg": {"properties": {"username": {}, "full_name": {}}}},
        "paths": {"/orgs": {"post": {
            "summary": "Create org",
            "parameters": [{"name": "body", "in": "body",
                            "schema": {"$ref": "#/definitions/NewOrg"}}],
        }}},
    }
    eps = targets.summarize_endpoints(spec)
    assert eps[0]["body_fields"] == ["username", "full_name"]


def test_summarize_endpoints_wordpress_routes():
    spec = {"routes": {"/wp/v2/posts": {"endpoints": [
        {"methods": ["GET"], "args": {"search": {"type": "string"}}},
        {"methods": ["POST"], "args": {"title": {}, "content": {}}},
    ]}}}
    eps = targets.summarize_endpoints(spec)
    methods = {e["method"] for e in eps}
    assert methods == {"GET", "POST"}
    post = next(e for e in eps if e["method"] == "POST")
    assert "title" in post["body_fields"]
    assert all(e["path"] == "/wp-json/wp/v2/posts" for e in eps)  # /wp-json prefix applied


def test_base_path_prepended_swagger2():
    spec = {"swagger": "2.0", "basePath": "/api/v1",
            "paths": {"/orgs": {"get": {"summary": "list orgs"}}}}
    eps = targets.summarize_endpoints(spec)
    assert eps[0]["path"] == "/api/v1/orgs"


def test_base_path_prepended_openapi3_servers():
    spec = {"openapi": "3.0.0", "servers": [{"url": "http://h:3000/api/v3"}],
            "paths": {"/repos": {"get": {"summary": "list"}}}}
    eps = targets.summarize_endpoints(spec)
    assert eps[0]["path"] == "/api/v3/repos"


def test_base_path_absent_is_noop():
    spec = {"openapi": "3.0.0", "paths": {"/x": {"get": {}}}}
    assert targets.summarize_endpoints(spec)[0]["path"] == "/x"


def test_endpoint_digest_compact():
    eps = targets.summarize_endpoints(OPENAPI3)
    digest = targets.endpoint_digest(eps)
    assert "GET /api/v1/repos/search" in digest
    assert "q(query)" in digest


def test_normalize_manual_shorthand_and_path_params():
    eps = targets.normalize_manual([
        {"method": "get", "path": "/api/user/{id}", "params": {"p": "query"}},
        {"method": "POST", "path": "/api/user/", "body_fields": ["username", "email"]},
        {"path": None},
    ])
    assert len(eps) == 2
    assert eps[0]["method"] == "GET"
    assert eps[0]["params"]["id"] == {"in": "path", "required": True, "type": "string", "desc": ""}
    assert eps[0]["params"]["p"]["in"] == "query"
    assert eps[1]["body_fields"] == ["username", "email"]


# ---------- APIExecutor helpers ----------

def test_fill_path_substitution_and_aliases():
    path, used, missing = APIExecutor._fill_path("/api/repos/{owner}/{repo}", {"owner": "a", "repo": "b"})
    assert path == "/api/repos/a/b" and used == {"owner", "repo"} and missing is None
    # {id} tolerates *_id aliases
    path, used, missing = APIExecutor._fill_path("/api/orders/{id}", {"order_id": 7})
    assert path == "/api/orders/7" and missing is None
    _, _, missing = APIExecutor._fill_path("/api/orders/{id}", {})
    assert missing == "id"


def test_rows_normalization():
    assert _rows([{"a": 1}]) == [{"a": 1}]
    assert _rows({"items": [{"a": 1}]}) == [{"a": 1}]
    assert _rows({"data": [1, 2]}) == [{"value": 1}, {"value": 2}]
    assert _rows({"total": 3}) == [{"total": 3}]
    assert _rows("x") == [{"value": "x"}]
    # single-object envelope unwrapped one level (new-api style)
    assert _rows({"data": {"username": "root", "quota": 100}, "success": True}) == \
        [{"username": "root", "quota": 100}]
    # nested list inside a data-envelope is unwrapped through to the rows
    assert _rows({"data": {"items": [{"a": 1}]}}) == [{"a": 1}]


def test_truncate_caps_payload():
    big = {"k": "v" * 10000}
    out = _truncate(big)
    assert out["_truncated"] is True and len(out["preview"]) <= 4000
    assert _truncate({"k": "v"}) == {"k": "v"}


# ---------- probe/discover against a mocked transport ----------

@pytest.mark.asyncio
async def test_validate_endpoints_keeps_real_drops_hallucinated(monkeypatch):
    # live target: /api/v1/users exists (200), /api/v1/ghost is 404, SPA returns HTML 200
    async def fake_request(self, method, path, **kw):
        if path == "/api/v1/users":
            return httpx.Response(200, json=[{"id": 1}])
        if path == "/api/v1/spa":
            return httpx.Response(200, text="<!doctype html>", headers={"content-type": "text/html"})
        return httpx.Response(404)

    class FakeClient:
        def __init__(self, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        request = fake_request

    monkeypatch.setattr(targets, "client_for", lambda cfg, **kw: FakeClient())
    proposed = [
        {"method": "GET", "path": "/api/v1/users", "summary": "real"},
        {"method": "GET", "path": "/api/v1/ghost", "summary": "hallucinated"},
        {"method": "GET", "path": "/api/v1/spa", "summary": "spa fallback"},
        {"method": "POST", "path": "/api/v1/users", "summary": "create (sibling of real)"},
        {"method": "POST", "path": "/api/v1/ghosts", "summary": "write with no live sibling"},
    ]
    kept = await targets.validate_endpoints({"base_url": "http://x"}, targets.normalize_manual(proposed))
    paths = {(e["method"], e["path"]) for e in kept}
    verified = {(e["method"], e["path"]) for e in kept if e.get("verified")}
    assert ("GET", "/api/v1/users") in paths          # real read kept
    assert ("GET", "/api/v1/ghost") not in paths       # 404 dropped
    assert ("GET", "/api/v1/spa") not in paths          # HTML SPA-fallback dropped
    # writes are NEVER probed (side effects) → ALL proposed writes are kept for
    # comprehensive coverage; they run only after human approval + honest failure.
    assert ("POST", "/api/v1/users") in paths
    assert ("POST", "/api/v1/ghosts") in paths
    assert ("POST", "/api/v1/users") in verified       # sibling read confirmed → higher confidence
    assert ("POST", "/api/v1/ghosts") not in verified  # no live sibling → kept but unverified


@pytest.mark.asyncio
async def test_discover_spec_common_path(monkeypatch):
    async def fake_get(self, path, **kw):
        if path == "/openapi.json":
            return httpx.Response(200, json=OPENAPI3)
        return httpx.Response(404)

    class FakeClient:
        def __init__(self, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        get = fake_get

    monkeypatch.setattr(targets, "client_for", lambda cfg, **kw: FakeClient())
    url, spec = await targets.discover_spec({"base_url": "http://x"})
    assert url == "/openapi.json"
    assert spec["openapi"] == "3.0.0"


# ---------- type coercion + cross-step ref resolution ----------

def test_coerce_types():
    from app.executors.base import _coerce
    assert _coerce("3", "integer") == 3
    assert _coerce("3", "array") == [3]
    assert _coerce("a,b", "array") == ["a", "b"]
    assert _coerce("[1,2]", "array") == [1, 2]
    assert _coerce("true", "boolean") is True
    assert _coerce("keep", "string") == "keep"
    assert _coerce(5, "integer") == 5           # non-str passthrough
    assert _coerce("x", "integer") == "x"        # unparseable → unchanged


def test_resolve_cross_step_refs():
    from app.agents.orchestrator import _resolve_refs
    step_rows = {1: [{"base_id": "abc", "id": 7}], 2: [{"id": 42}]}
    out = _resolve_refs({"a": "$step1.base_id", "b": "$2", "c": "$prev.id",
                         "d": "literal", "e": ["$step1.id", "x"]}, step_rows)
    assert out["a"] == "abc"
    assert out["b"] == "42"           # $2 → step 2 first row id
    assert out["c"] == 42             # $prev.id → latest step's field
    assert out["d"] == "literal"
    assert out["e"] == [7, "x"]
    # unresolved ref (no such step) left as-is so it surfaces at the executor
    assert _resolve_refs({"x": "$step9.foo"}, step_rows)["x"] == "$step9.foo"


# ---------- kind inference + honesty + map responses ----------

def test_infer_kind_semantic():
    from app.services.explorer import _infer_kind
    assert _infer_kind("GET", "user.list", "list users", "/users", "") == "query"
    assert _infer_kind("DELETE", "x", "", "", "") == "mutation"
    # Metabase-style POST reads → query
    assert _infer_kind("POST", "search.find", "search saved questions", "/api/agent/v1/search", "") == "query"
    assert _infer_kind("POST", "query.execute", "run a dataset query", "/api/dataset", "") == "query"
    # POST creates/updates → mutation even with a read-ish word nearby
    assert _infer_kind("POST", "card.create", "create a new question", "/api/card", "") == "mutation"
    assert _infer_kind("PUT", "user.update", "update user", "/users/{id}", "") == "mutation"
    # ambiguous POST with no signal → safe default mutation
    assert _infer_kind("POST", "thing.do", "", "/x", "") == "mutation"


def test_rows_map_of_lists_flattened():
    # new-api /api/models style: {"data":{"1":[{..}],"37":[{..}]}}
    payload = {"data": {"1": [{"id": "gpt-a"}], "37": [{"id": "gpt-b"}, {"id": "gpt-c"}]}, "success": True}
    rows = _rows(payload)
    assert len(rows) == 3
    assert {r["id"] for r in rows} == {"gpt-a", "gpt-b", "gpt-c"}


def test_function_executor_unknown_op_is_not_fake_success():
    import asyncio
    from app.executors.base import FunctionExecutor
    fx = FunctionExecutor()
    # unknown write op → honest not_connected error, never fake success
    res = asyncio.run(fx.execute(None, None, "row.create", {"x": 1}))
    assert res.error_code == "not_connected"
    # unknown read op → error envelope, not empty "no data"
    rows = asyncio.run(fx.read(None, None, "row.query", {}))
    assert rows == [{"error": "not_connected"}]


def test_looks_like_write_intent():
    from app.api.chat import _looks_like_write
    assert _looks_like_write("帮我新建一个工单")
    assert _looks_like_write("把状态改成已完成")
    assert _looks_like_write("create a new repo")
    assert not _looks_like_write("列出所有的仓库")
    assert not _looks_like_write("有哪些用户")


def test_api_body_error_detection():
    from app.executors.base import api_body_error
    # new-api style: HTTP 200 but success:false
    assert api_body_error({"success": False, "message": "json: cannot unmarshal string"}) == "json: cannot unmarshal string"
    assert api_body_error({"ok": False, "error": "bad"}) is not None
    assert api_body_error({"error": "not found"}) == "not found"
    assert api_body_error({"errno": 500, "msg": "boom"}) == "boom"
    # genuine successes → no error
    assert api_body_error({"success": True, "data": {"id": 1}}) is None
    assert api_body_error({"items": [1, 2, 3]}) is None
    assert api_body_error({"id": 1, "name": "x"}) is None
    assert api_body_error([{"id": 1}]) is None      # list payload
    assert api_body_error({"code": 200, "data": []}) is None  # code=200 not treated as error


def test_risk_policy_by_operation():
    from app.services.explorer import _risk_policy
    # reads: broad, auto
    risk, confirm, grants = _risk_policy("query", "repo.list", "GET")
    assert risk == "low" and confirm == "auto"
    assert ("customer", "self") in grants
    # ordinary write: confirm, staff+admin
    risk, confirm, grants = _risk_policy("mutation", "repo.create", "POST")
    assert risk == "high" and confirm == "confirm"
    assert ("employee", None) in grants and ("admin", None) in grants
    # destructive: dual approval, admins ONLY
    risk, confirm, grants = _risk_policy("mutation", "repo.delete", "DELETE")
    assert risk == "critical" and confirm == "dual"
    assert grants == [("admin", None)]
    # admin/security-sensitive change: also dual + admin-only
    risk, confirm, grants = _risk_policy("mutation", "user.ban", "POST")
    assert confirm == "dual" and grants == [("admin", None)]
    risk, confirm, grants = _risk_policy("mutation", "channel.update", "PUT")
    assert confirm == "dual"  # 'channel' is billing-sensitive in _ADMIN_AREA


@pytest.mark.asyncio
async def test_write_prefix_aligned_to_confirmed_read(monkeypatch):
    # new-api style: reads live at /api/token/ (no v1), LLM guessed write at /api/v1/token
    async def fake_request(self, method, path, **kw):
        if path == "/api/token/1" or path == "/api/token/":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    class FakeClient:
        def __init__(self, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        request = fake_request

    monkeypatch.setattr(targets, "client_for", lambda cfg, **kw: FakeClient())
    proposed = targets.normalize_manual([
        {"method": "GET", "path": "/api/token/", "summary": "list tokens"},
        {"method": "POST", "path": "/api/v1/token", "summary": "create token"},   # wrong prefix
    ])
    kept = await targets.validate_endpoints({"base_url": "http://x"}, proposed)
    post = next(e for e in kept if e["method"] == "POST")
    assert post["path"] == "/api/token"          # aligned to the confirmed read's /api prefix
    assert post["prefix_corrected"] is True


def test_api_prefix_split():
    assert targets._api_prefix_split("/api/v1/token") == ("/api/v1", "/token")
    assert targets._api_prefix_split("/api/token/") == ("/api", "/token/")
    assert targets._api_prefix_split("/v4/users") == ("/v4", "/users")
    assert targets._api_prefix_split("/users") == ("", "/users")


@pytest.mark.asyncio
async def test_login_auth_acquires_and_caches_session_token(monkeypatch):
    # a system whose auth = POST /api/auth {password} → {session:{sid}}, header X-FTL-SID
    calls = {"login": 0}

    class FakeResp:
        def __init__(self, data): self._d = data
        def json(self): return self._d

    class FakeClient:
        def __init__(self, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def request(self, method, url, **kw):
            calls["login"] += 1
            assert url == "/api/auth" and kw.get("json") == {"password": "sekret"}
            return FakeResp({"session": {"valid": True, "sid": "SID-123", "csrf": "x"}})

    monkeypatch.setattr(targets.httpx, "AsyncClient", lambda **kw: FakeClient())
    monkeypatch.setenv("TGT_PH", "sekret")
    targets._login_cache.clear()
    cfg = {"base_url": "http://x", "auth": {
        "kind": "login", "login_url": "/api/auth", "login_body": {"password": "$secret"},
        "token_path": "session.sid", "header": "X-FTL-SID", "secret_env": "TGT_PH"}}
    await targets.ensure_login_token(cfg)
    h = targets.build_auth_headers(cfg)
    assert h["X-FTL-SID"] == "SID-123"
    # cached — a 2nd ensure does not re-login
    await targets.ensure_login_token(cfg)
    assert calls["login"] == 1
    # force re-login
    await targets.ensure_login_token(cfg, force=True)
    assert calls["login"] == 2


@pytest.mark.asyncio
async def test_login_auth_extracts_token_from_cookie(monkeypatch):
    # Vaultwarden-style: POST /admin (form) → Set-Cookie VW_ADMIN=<jwt>, sent as a
    # Cookie header. The token lives in the cookie jar, not the JSON body.
    class FakeResp:
        cookies: dict = {}
        def json(self): raise ValueError("no json body")

    class FakeClient:
        def __init__(self, **kw): self.cookies = {"VW_ADMIN": "jwt-xyz"}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def request(self, method, url, **kw):
            assert kw.get("data") == {"token": "adminpw"}   # form-encoded, not json
            return FakeResp()

    monkeypatch.setattr(targets.httpx, "AsyncClient", lambda **kw: FakeClient())
    monkeypatch.setenv("TGT_VW", "adminpw")
    targets._login_cache.clear()
    cfg = {"base_url": "http://x", "auth": {
        "kind": "login", "login_url": "/admin", "login_method": "POST",
        "login_form": True, "login_body": {"token": "$secret"},
        "token_from": "cookie", "cookie_name": "VW_ADMIN",
        "header": "Cookie", "prefix": "VW_ADMIN=", "secret_env": "TGT_VW"}}
    await targets.ensure_login_token(cfg)
    h = targets.build_auth_headers(cfg)
    assert h["Cookie"] == "VW_ADMIN=jwt-xyz"
