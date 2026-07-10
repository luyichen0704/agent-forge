"""GraphQL API-surface discovery — the framework's GraphQL transport.

A GraphQL API exposes its ENTIRE surface through one endpoint plus a machine-
readable schema (introspection), so discovery is authoritative and needs no
LLM guessing: every root Query field becomes a read op, every Mutation field a
write op. Each field is emitted as a pseudo-"endpoint" dict so it flows through
the SAME naming → risk-policy → registration pipeline as a REST endpoint —
only the executor binding differs (GraphQLExecutor instead of APIExecutor).

Gate: a source whose config carries `graphql_url` uses this instead of the
REST spec/probe path. Zero per-system code — proven against Directus, Saleor,
Hasura, GitHub GraphQL, or any spec-compliant GraphQL server.
"""
from __future__ import annotations

from typing import Any

from . import targets

# One introspection call returns the whole type system. We only need root
# Query/Mutation fields (+ their args and return types) and, for building a
# default selection set, each object type's scalar leaf fields — so the TypeRef
# fragment is resolved to the depth GraphQL nesting (NON_NULL/LIST) reaches.
_TYPEREF = """
  kind name
  ofType { kind name ofType { kind name ofType { kind name
    ofType { kind name ofType { kind name ofType { kind name } } } } } }
"""

INTROSPECTION_QUERY = (
    "query { __schema { "
    "queryType { name } mutationType { name } "
    "types { kind name "
    "fields(includeDeprecated: false) { name "
    f"args {{ name type {{ {_TYPEREF} }} }} "
    f"type {{ {_TYPEREF} }} }} "
    "} } }"
)


def _named(type_ref: dict | None) -> dict | None:
    """Strip NON_NULL / LIST wrappers → the underlying named type node."""
    t = type_ref
    while t and t.get("name") is None and t.get("ofType"):
        t = t["ofType"]
    return t if (t and t.get("name")) else None


def _type_str(type_ref: dict | None) -> str:
    """Render an introspection type node back to GraphQL SDL, e.g.
    NON_NULL(LIST(NON_NULL(User))) → "[User!]!". Used for variable decls."""
    if not type_ref:
        return "String"
    kind = type_ref.get("kind")
    if kind == "NON_NULL":
        return _type_str(type_ref.get("ofType")) + "!"
    if kind == "LIST":
        return "[" + _type_str(type_ref.get("ofType")) + "]"
    return type_ref.get("name") or "String"


def _scalar_leaves(type_ref: dict | None, types_by_name: dict[str, dict]) -> str:
    """A named object type's own scalar/enum leaf fields (no args, not nested) —
    a flat, always-valid row. Empty when the type is a scalar/enum itself."""
    named = _named(type_ref)
    if not named:
        return ""
    tdef = types_by_name.get(named["name"])
    if not tdef or tdef.get("kind") not in ("OBJECT", "INTERFACE"):
        return ""   # scalar / enum return — field(args) with no sub-selection
    leaves: list[str] = []
    for f in tdef.get("fields") or []:
        if f.get("args"):
            continue                      # a leaf that needs args is not a plain column
        ftn = _named(f.get("type"))
        if not ftn:
            continue
        inner = types_by_name.get(ftn["name"])
        if inner and inner.get("kind") in ("SCALAR", "ENUM"):
            leaves.append(f["name"])
    return " ".join(leaves[:24])


def _selection(type_ref: dict | None, types_by_name: dict[str, dict]) -> str:
    """Default selection set for a field's return type. Handles the two shapes
    that cover almost all GraphQL reads:
      • a plain object/list → its scalar leaf columns
      • a Relay connection ({ totalCount, edges { node } }, as Saleor/Shopify/
        GitHub use) → totalCount + edges.node's scalar leaves, so a "list X"
        query returns the actual business rows, not just a count wrapper.
    Empty string for a scalar return (no sub-selection needed)."""
    named = _named(type_ref)
    if not named:
        return ""
    tdef = types_by_name.get(named["name"])
    if not tdef or tdef.get("kind") not in ("OBJECT", "INTERFACE"):
        return ""
    fnames = {f.get("name"): f for f in (tdef.get("fields") or [])}
    edges_f = fnames.get("edges")
    if edges_f is not None:                       # looks like a Relay connection
        edge_t = types_by_name.get((_named(edges_f.get("type")) or {}).get("name", ""))
        node_f = next((f for f in (edge_t or {}).get("fields") or []
                       if f.get("name") == "node"), None) if edge_t else None
        node_leaves = _scalar_leaves(node_f.get("type"), types_by_name) if node_f else ""
        if node_leaves:
            tc = "totalCount " if "totalCount" in fnames else ""
            return f"{tc}edges {{ node {{ {node_leaves} }} }}"
    return _scalar_leaves(type_ref, types_by_name)


async def discover_graphql(config: dict) -> list[dict]:
    """Introspect the GraphQL endpoint and return pseudo-endpoint dicts, one per
    root Query/Mutation field, ready for the naming+registration pipeline.
    Returns [] if the endpoint is unreachable or introspection is disabled."""
    url = (config or {}).get("graphql_url")
    if not url:
        return []
    await targets.ensure_login_token(config)
    async with targets.client_for(config) as client:
        resp = await client.post(url, json={"query": INTROSPECTION_QUERY})
    if resp.status_code >= 300:
        return []
    try:
        schema = (resp.json().get("data") or {}).get("__schema") or {}
    except ValueError:
        return []
    if not schema:
        return []

    types = schema.get("types") or []
    types_by_name = {t["name"]: t for t in types if t.get("name")}
    roots = [
        ("query", (schema.get("queryType") or {}).get("name")),
        ("mutation", (schema.get("mutationType") or {}).get("name")),
    ]

    endpoints: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for gql_type, root_name in roots:
        if not root_name:
            continue
        root = types_by_name.get(root_name)
        if not root:
            continue
        for f in root.get("fields") or []:
            name = f.get("name")
            if not name or name.startswith("__"):
                continue
            method = gql_type.upper()
            if (method, name) in seen:
                continue
            seen.add((method, name))
            arg_types = {a["name"]: _type_str(a.get("type"))
                         for a in (f.get("args") or []) if a.get("name")}
            endpoints.append({
                "method": method,            # QUERY / MUTATION — the pseudo-verb
                "path": name,                # the root field name
                "transport": "graphql",
                "gql_type": gql_type,
                "graphql_url": url,
                "selection": _selection(f.get("type"), types_by_name),
                "arg_types": arg_types,
                # params/summary feed the LLM naming digest — same shape REST uses
                # ({in, required, type}), so the shared digest formatter works.
                "params": {a: {"in": "arg", "required": t.endswith("!"), "type": t}
                           for a, t in arg_types.items()},
                "summary": f"GraphQL {gql_type} → {_type_str(f.get('type'))}",
            })
    return endpoints
