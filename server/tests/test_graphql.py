"""Unit tests for the GraphQL transport (services/graphql_disco + GraphQLExecutor).

Covers the extensibility path that lets the frozen adaptation pipeline speak
GraphQL: introspection → pseudo-endpoints → deterministic ops → document build.
"""
import httpx
import pytest

from app.executors.base import GraphQLExecutor, _gql_coerce
from app.services import graphql_disco as g
from app.services import targets


# ---------- type rendering + selection derivation (pure) ----------

def test_type_str_renders_sdl_wrappers():
    ref = {"kind": "NON_NULL", "ofType": {"kind": "LIST", "ofType":
           {"kind": "NON_NULL", "ofType": {"kind": "OBJECT", "name": "User"}}}}
    assert g._type_str(ref) == "[User!]!"
    assert g._type_str({"kind": "SCALAR", "name": "Int"}) == "Int"
    assert g._type_str(None) == "String"


def test_scalar_leaves_selects_only_plain_columns():
    tmap = {
        "User": {"kind": "OBJECT", "fields": [
            {"name": "id", "args": [], "type": {"kind": "SCALAR", "name": "ID"}},
            {"name": "email", "args": [], "type": {"kind": "SCALAR", "name": "String"}},
            {"name": "posts", "args": [], "type": {"kind": "LIST", "ofType":
                {"kind": "OBJECT", "name": "Post"}}},                    # nested object → skip
            {"name": "avatar", "args": [{"name": "size"}],
             "type": {"kind": "SCALAR", "name": "String"}},             # needs args → skip
        ]},
        "ID": {"kind": "SCALAR"}, "String": {"kind": "SCALAR"}, "Post": {"kind": "OBJECT"},
    }
    ref = {"kind": "LIST", "ofType": {"kind": "OBJECT", "name": "User"}}
    assert g._scalar_leaves(ref, tmap) == "id email"


def test_scalar_leaves_empty_for_scalar_return():
    assert g._scalar_leaves({"kind": "SCALAR", "name": "Int"}, {"Int": {"kind": "SCALAR"}}) == ""


def test_selection_relay_connection_reaches_node_fields():
    # Saleor/Shopify/GitHub shape: Query.products -> ProductCountableConnection
    # { totalCount, edges { node: Product } }. Selection must dig into node.
    tmap = {
        "ProductConnection": {"kind": "OBJECT", "fields": [
            {"name": "totalCount", "args": [], "type": {"kind": "SCALAR", "name": "Int"}},
            {"name": "edges", "args": [], "type": {"kind": "LIST", "ofType":
                {"kind": "OBJECT", "name": "ProductEdge"}}},
        ]},
        "ProductEdge": {"kind": "OBJECT", "fields": [
            {"name": "node", "args": [], "type": {"kind": "OBJECT", "name": "Product"}},
        ]},
        "Product": {"kind": "OBJECT", "fields": [
            {"name": "id", "args": [], "type": {"kind": "SCALAR", "name": "ID"}},
            {"name": "name", "args": [], "type": {"kind": "SCALAR", "name": "String"}},
        ]},
        "Int": {"kind": "SCALAR"}, "ID": {"kind": "SCALAR"}, "String": {"kind": "SCALAR"},
    }
    sel = g._selection({"kind": "OBJECT", "name": "ProductConnection"}, tmap)
    assert sel == "totalCount edges { node { id name } }"


# ---------- introspection discovery ----------

_INTROSPECTION = {
    "data": {"__schema": {
        "queryType": {"name": "Query"},
        "mutationType": {"name": "Mutation"},
        "types": [
            {"kind": "OBJECT", "name": "Query", "fields": [
                {"name": "users", "args": [{"name": "limit", "type": {"kind": "SCALAR", "name": "Int"}}],
                 "type": {"kind": "LIST", "ofType": {"kind": "OBJECT", "name": "User"}}},
                {"name": "__stripped", "args": [], "type": {"kind": "SCALAR", "name": "String"}},
            ]},
            {"kind": "OBJECT", "name": "Mutation", "fields": [
                {"name": "create_user",
                 "args": [{"name": "email", "type": {"kind": "NON_NULL", "ofType": {"kind": "SCALAR", "name": "String"}}}],
                 "type": {"kind": "OBJECT", "name": "User"}},
            ]},
            {"kind": "OBJECT", "name": "User", "fields": [
                {"name": "id", "args": [], "type": {"kind": "SCALAR", "name": "ID"}},
                {"name": "email", "args": [], "type": {"kind": "SCALAR", "name": "String"}},
            ]},
            {"kind": "SCALAR", "name": "ID"}, {"kind": "SCALAR", "name": "String"},
            {"kind": "SCALAR", "name": "Int"},
        ],
    }},
}


def _fake_client(post_response):
    class FakeClient:
        def __init__(self, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw): return post_response
    return lambda cfg, **kw: FakeClient()


@pytest.mark.asyncio
async def test_discover_graphql_maps_fields(monkeypatch):
    monkeypatch.setattr(targets, "client_for", _fake_client(httpx.Response(200, json=_INTROSPECTION)))
    monkeypatch.setattr(targets, "ensure_login_token", _noop)
    eps = await g.discover_graphql({"graphql_url": "/graphql/", "base_url": "http://x"})
    by = {(e["method"], e["path"]): e for e in eps}
    # __-prefixed introspection field is dropped
    assert ("QUERY", "__stripped") not in by
    users = by[("QUERY", "users")]
    assert users["gql_type"] == "query"
    assert users["selection"] == "id email"          # object return → scalar leaves
    assert users["arg_types"] == {"limit": "Int"}
    assert users["transport"] == "graphql"
    create = by[("MUTATION", "create_user")]
    assert create["gql_type"] == "mutation"
    assert create["arg_types"] == {"email": "String!"}   # NON_NULL rendered
    assert create["params"]["email"]["required"] is True


@pytest.mark.asyncio
async def test_discover_graphql_empty_on_disabled_introspection(monkeypatch):
    monkeypatch.setattr(targets, "client_for", _fake_client(httpx.Response(400, text="off")))
    monkeypatch.setattr(targets, "ensure_login_token", _noop)
    assert await g.discover_graphql({"graphql_url": "/graphql/"}) == []


# ---------- document building + coercion (pure) ----------

def test_build_document_query_with_args_and_selection():
    b = {"field": "users", "gql_type": "query", "selection": "id email",
         "arg_types": {"limit": "Int", "filter": "users_filter"}}
    doc, vars = GraphQLExecutor._build_document(b, {"limit": "3", "bogus": "x"})
    assert doc == "query($limit: Int) { users(limit: $limit) { id email } }"
    assert vars == {"limit": 3}          # coerced to Int; unknown arg dropped


def test_build_document_injects_default_page_for_relay_connection():
    # a "list products" connection query with no page arg supplied → default first:50
    b = {"field": "products", "gql_type": "query",
         "selection": "totalCount edges { node { id name } }",
         "arg_types": {"first": "Int", "channel": "String"}}
    doc, vars = GraphQLExecutor._build_document(b, {})
    assert vars == {"first": 50}
    assert "products(first: $first)" in doc
    # caller-supplied page size wins (no override)
    doc2, vars2 = GraphQLExecutor._build_document(b, {"first": "5"})
    assert vars2 == {"first": 5}


def test_build_document_scalar_return_no_selection():
    b = {"field": "server_ping", "gql_type": "query", "selection": "", "arg_types": {}}
    doc, _ = GraphQLExecutor._build_document(b, {})
    assert doc == "query { server_ping }"


def test_build_document_mutation():
    b = {"field": "create_user", "gql_type": "mutation", "selection": "id",
         "arg_types": {"email": "String!"}}
    doc, vars = GraphQLExecutor._build_document(b, {"email": "a@b.c"})
    assert doc == "mutation($email: String!) { create_user(email: $email) { id } }"
    assert vars == {"email": "a@b.c"}


def test_gql_coerce_types():
    assert _gql_coerce("3", "Int") == 3
    assert _gql_coerce("2.5", "Float") == 2.5
    assert _gql_coerce("true", "Boolean") is True
    assert _gql_coerce("x", "[ID!]") == "x"          # non-scalar base left as-is (best effort)
    assert _gql_coerce("keep", "String") == "keep"


# ---------- executor read: envelope + errors ----------

@pytest.mark.asyncio
async def test_graphql_read_unwraps_field_and_honest_errors(monkeypatch):
    ex = GraphQLExecutor()
    binding = {"source_id": "0" * 32, "field": "users", "gql_type": "query",
               "selection": "id", "arg_types": {}, "graphql_url": "/graphql/"}

    async def resolve(self, db, tid, key): return binding, {"base_url": "http://x"}
    monkeypatch.setattr(GraphQLExecutor, "_resolve", resolve)

    # success: data.users list → rows
    monkeypatch.setattr(targets, "client_for",
                        _fake_client(httpx.Response(200, json={"data": {"users": [{"id": 1}, {"id": 2}]}})))
    monkeypatch.setattr(targets, "ensure_login_token", _noop)
    rows = await ex.read(None, None, "users", {})
    assert rows == [{"id": 1}, {"id": 2}]

    # GraphQL errors → honest failure surfaced, never masked as empty success
    monkeypatch.setattr(targets, "client_for",
                        _fake_client(httpx.Response(200, json={"errors": [{"message": "denied"}]})))
    rows = await ex.read(None, None, "users", {})
    assert rows == [{"error": "graphql_error:denied"}]


@pytest.mark.asyncio
async def test_graphql_read_unwraps_relay_connection(monkeypatch):
    ex = GraphQLExecutor()
    binding = {"source_id": "0" * 32, "field": "products", "gql_type": "query",
               "selection": "totalCount edges { node { id name } }", "arg_types": {},
               "graphql_url": "/graphql/"}

    async def resolve(self, db, tid, key): return binding, {"base_url": "http://x"}
    monkeypatch.setattr(GraphQLExecutor, "_resolve", resolve)
    monkeypatch.setattr(targets, "ensure_login_token", _noop)
    conn = {"data": {"products": {"totalCount": 42, "edges": [
        {"node": {"id": "1", "name": "Widget"}}, {"node": {"id": "2", "name": "Gadget"}}]}}}
    monkeypatch.setattr(targets, "client_for", _fake_client(httpx.Response(200, json=conn)))
    meta: dict = {}
    rows = await ex.read(None, None, "products", {}, meta)
    assert rows == [{"id": "1", "name": "Widget"}, {"id": "2", "name": "Gadget"}]  # edges[].node
    assert meta["total"] == 42                            # totalCount → grand-total


async def _noop(*a, **kw):
    return None
