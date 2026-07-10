"""Unit tests for the XML-RPC transport (services/xmlrpc_disco + XMLRPCExecutor).

Odoo isn't required — the RPC calls are mocked so the discovery→binding→execute
logic is validated deterministically.
"""
import xmlrpc.client

import pytest

from app.executors import base
from app.executors.base import XMLRPCExecutor
from app.services import xmlrpc_disco as x
from app.services.explorer import _xmlrpc_ops_list


def _fake_execute_factory():
    """Return a fake _execute keyed on (model, method)."""
    def _exec(base_url, db, uid, pw, model, method, args, kwargs=None):
        if model == "ir.model" and method == "search_read":
            return [{"model": "res.partner", "name": "联系人"},
                    {"model": "ir.ui.view", "name": "View"},      # technical → filtered
                    {"model": "sale.order", "name": "销售订单"}]
        if method == "fields_get":
            return {"id": {"type": "integer"}, "name": {"type": "char"},
                    "email": {"type": "char"}, "child_ids": {"type": "one2many"}}
        return None
    return _exec


@pytest.mark.asyncio
async def test_discover_xmlrpc_emits_crud_per_business_model(monkeypatch):
    monkeypatch.setattr(x, "_authenticate", lambda *a: 7)
    monkeypatch.setattr(x, "_execute", _fake_execute_factory())
    cfg = {"base_url": "http://odoo", "xmlrpc": {"db": "odoo", "username": "admin", "password": "admin"}}
    eps = await x.discover_xmlrpc(cfg)
    models = {e["model"] for e in eps}
    assert "res.partner" in models and "sale.order" in models
    assert "ir.ui.view" not in models                       # technical prefix filtered
    partner = [e for e in eps if e["model"] == "res.partner"]
    assert {e["path"] for e in partner} == {
        "res.partner.search", "res.partner.count", "res.partner.create",
        "res.partner.update", "res.partner.delete"}
    search = next(e for e in partner if e["rpc_method"] == "search_read")
    assert search["op_kind"] == "query"
    assert "email" in search["fields"] and "child_ids" not in search["fields"]  # scalar only
    create = next(e for e in partner if e["rpc_method"] == "create")
    assert create["op_kind"] == "mutation"


@pytest.mark.asyncio
async def test_discover_xmlrpc_empty_on_auth_fail(monkeypatch):
    monkeypatch.setattr(x, "_authenticate", lambda *a: None)
    assert await x.discover_xmlrpc(
        {"base_url": "http://x", "xmlrpc": {"db": "d", "username": "u", "password": "p"}}) == []


def test_xmlrpc_ops_list_deterministic_names():
    eps = [
        {"path": "sale.order.search", "method": "RPC", "op_kind": "query",
         "model": "sale.order", "summary": "销售订单 · search"},
        {"path": "sale.order.delete", "method": "RPC", "op_kind": "mutation",
         "model": "sale.order", "summary": "销售订单 · delete"},
    ]
    ops = {o["key"]: o for o in _xmlrpc_ops_list(eps)}
    assert ops["sale.order.search"]["desc"] == "查询销售订单"
    assert ops["sale.order.search"]["kind"] == "query"
    assert ops["sale.order.delete"]["desc"] == "删除销售订单"
    assert ops["sale.order.delete"]["kind"] == "mutation"


def test_domain_builder_from_flat_kwargs():
    ex = XMLRPCExecutor()
    assert ex._domain({"name": "Acme", "limit": 10, "user_id": 3}) == [["name", "=", "Acme"]]
    assert ex._domain({"domain": [["active", "=", True]]}) == [["active", "=", True]]


@pytest.mark.asyncio
async def test_xmlrpc_read_rows_count_and_honest_error(monkeypatch):
    ex = XMLRPCExecutor()
    binding = {"source_id": "0" * 32, "transport": "xmlrpc", "model": "res.partner",
               "rpc_method": "search_read", "op_kind": "query", "fields": ["id", "name"]}
    cfg = {"base_url": "http://odoo", "xmlrpc": {"db": "odoo", "username": "admin", "password": "admin"}}

    async def resolve(self, db, tid, key): return binding, cfg
    monkeypatch.setattr(XMLRPCExecutor, "_resolve", resolve)
    base._XMLRPC_UID.clear()
    monkeypatch.setattr(x, "_authenticate", lambda *a: 7)

    # search_read → list of dicts becomes rows
    monkeypatch.setattr(x, "_execute", lambda *a, **k: [{"id": 1, "name": "Acme"}, {"id": 2, "name": "Globex"}])
    rows = await ex.read(None, None, "res.partner.search", {})
    assert rows == [{"id": 1, "name": "Acme"}, {"id": 2, "name": "Globex"}]

    # search_count → int surfaced as total + a count row
    binding["rpc_method"] = "search_count"
    monkeypatch.setattr(x, "_execute", lambda *a, **k: 42)
    meta: dict = {}
    rows = await ex.read(None, None, "res.partner.count", {}, meta)
    assert rows == [{"count": 42}] and meta["total"] == 42

    # xmlrpc Fault → honest failure, never masked
    binding["rpc_method"] = "search_read"
    def _boom(*a, **k): raise xmlrpc.client.Fault(2, "access denied")
    monkeypatch.setattr(x, "_execute", _boom)
    rows = await ex.read(None, None, "res.partner.search", {})
    assert rows == [{"error": "rpc_error:access denied"}]


@pytest.mark.asyncio
async def test_xmlrpc_write_returns_result(monkeypatch):
    ex = XMLRPCExecutor()
    binding = {"source_id": "0" * 32, "transport": "xmlrpc", "model": "res.partner",
               "rpc_method": "create", "op_kind": "mutation", "fields": []}
    cfg = {"base_url": "http://odoo", "xmlrpc": {"db": "odoo", "username": "admin", "password": "admin"}}

    async def resolve(self, db, tid, key): return binding, cfg
    monkeypatch.setattr(XMLRPCExecutor, "_resolve", resolve)
    base._XMLRPC_UID.clear()
    monkeypatch.setattr(x, "_authenticate", lambda *a: 7)
    captured = {}
    def _exec(base_url, db, uid, pw, model, method, args, kwargs=None):
        captured.update(model=model, method=method, args=args)
        return 55                                            # new record id
    monkeypatch.setattr(x, "_execute", _exec)
    res = await ex.execute(None, None, "res.partner.create", {"name": "New Co", "limit": 9})
    assert res.error_code is None
    assert captured["method"] == "create"
    assert captured["args"] == [{"name": "New Co"}]          # meta key 'limit' dropped
