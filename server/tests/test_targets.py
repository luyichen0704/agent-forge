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


def test_truncate_caps_payload():
    big = {"k": "v" * 10000}
    out = _truncate(big)
    assert out["_truncated"] is True and len(out["preview"]) <= 4000
    assert _truncate({"k": "v"}) == {"k": "v"}


# ---------- probe/discover against a mocked transport ----------

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

    monkeypatch.setattr(targets, "client_for", lambda cfg: FakeClient())
    url, spec = await targets.discover_spec({"base_url": "http://x"})
    assert url == "/openapi.json"
    assert spec["openapi"] == "3.0.0"
