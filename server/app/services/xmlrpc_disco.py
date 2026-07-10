"""XML-RPC API-surface discovery — the framework's Odoo-style RPC transport.

Odoo (and other XML-RPC ERPs) expose no REST/OpenAPI: everything goes through
`execute_kw(db, uid, password, model, method, args)` over /xmlrpc/2/object. But
the surface is highly regular — every model supports the same CRUD verbs — so
discovery is authoritative without LLM guessing: list the business models, and
each model yields a fixed op set (search / count / create / update / delete).

Each op is emitted as a pseudo-endpoint (method=RPC, path=model.verb) so it flows
through the SAME naming/risk/registration pipeline as REST/GraphQL — only the
executor binding differs (XMLRPCExecutor). Gate: a source whose config carries an
`xmlrpc` block uses this. Zero per-system code.
"""
from __future__ import annotations

import asyncio
import os
import xmlrpc.client
from typing import Any

# models under these namespaces are technical plumbing, not business operations
_TECH_PREFIXES = (
    "ir.", "base_", "bus.", "web_", "web.", "report.", "mail.tracking",
    "mail.followers", "mail.message.", "mail.notification", "mail.alias",
    "res.groups", "res.users.", "res.config", "ir_", "fetchmail", "iap.",
    "format.", "barcode", "wizard", "_unknown", "res.lang", "res.currency.rate",
)
# a compact, always-safe default column set (display_name exists on every model)
_FALLBACK_FIELDS = ["id", "display_name"]
# odoo field types that read cleanly as flat columns
_SCALAR_TYPES = {"char", "text", "integer", "float", "monetary", "boolean",
                 "date", "datetime", "selection", "html"}


def resolve_xmlrpc_password(xr: dict) -> str | None:
    if xr.get("password"):
        return xr["password"]
    env = xr.get("password_env")
    return os.environ.get(env) if env else None


def _proxy(base_url: str, endpoint: str) -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(f"{base_url.rstrip('/')}/xmlrpc/2/{endpoint}",
                                     allow_none=True)


def _authenticate(base_url: str, db: str, user: str, password: str) -> int | None:
    try:
        uid = _proxy(base_url, "common").authenticate(db, user, password, {})
        return uid if isinstance(uid, int) and uid else None
    except Exception:  # noqa: BLE001 — unreachable / bad creds → no discovery
        return None


def _execute(base_url: str, db: str, uid: int, password: str,
             model: str, method: str, args: list, kwargs: dict | None = None) -> Any:
    return _proxy(base_url, "object").execute_kw(db, uid, password, model, method,
                                                 args, kwargs or {})


# the fixed CRUD verb set every Odoo model supports, mapped to op kind + risk hint
_VERBS = [
    ("search", "search_read", "query"),
    ("count", "search_count", "query"),
    ("create", "create", "mutation"),
    ("update", "write", "mutation"),
    ("delete", "unlink", "mutation"),
]


async def discover_xmlrpc(config: dict) -> list[dict]:
    """Authenticate, list business models, and emit CRUD pseudo-endpoints per
    model. Returns [] if the RPC endpoint is unreachable or auth fails."""
    xr = (config or {}).get("xmlrpc") or {}
    base_url = (config or {}).get("base_url") or ""
    db, user = xr.get("db"), xr.get("username")
    password = resolve_xmlrpc_password(xr)
    if not (base_url and db and user and password):
        return []

    def _work() -> list[dict]:
        uid = _authenticate(base_url, db, user, password)
        if not uid:
            return []
        try:
            models = _execute(base_url, db, uid, password, "ir.model", "search_read",
                              [[["transient", "=", False]]],
                              {"fields": ["model", "name"], "order": "model"})
        except Exception:  # noqa: BLE001
            return []
        eps: list[dict] = []
        for m in models:
            model = m.get("model") or ""
            if not model or model.startswith(_TECH_PREFIXES):
                continue
            # a compact scalar field set for readable rows (best-effort per model)
            fields = _FALLBACK_FIELDS
            try:
                fg = _execute(base_url, db, uid, password, model, "fields_get", [],
                              {"attributes": ["type", "string"]})
                cols = [f for f, meta in fg.items()
                        if meta.get("type") in _SCALAR_TYPES and not f.startswith("_")]
                if cols:
                    fields = (["id"] + [c for c in ("name", "display_name") if c in fg]
                              + [c for c in cols if c not in ("id", "name", "display_name")])[:10]
            except Exception:  # noqa: BLE001 — fall back to id+display_name
                pass
            for verb, rpc_method, kind in _VERBS:
                eps.append({
                    "method": "RPC", "path": f"{model}.{verb}",
                    "transport": "xmlrpc", "model": model,
                    "rpc_method": rpc_method, "op_kind": kind,
                    "fields": fields if rpc_method == "search_read" else [],
                    "summary": f"{m.get('name') or model} · {verb}",
                    "params": {},
                })
            if len(eps) >= 4000:          # hard safety cap (single call limit)
                break
        return eps

    return await asyncio.to_thread(_work)
