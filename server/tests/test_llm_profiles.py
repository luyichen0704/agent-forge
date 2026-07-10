"""Per-tenant LLM profile API + resolver (Task 14)."""
import httpx
import pytest

from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t/api/v1", timeout=30)


async def _login(c, role):
    return (await c.post("/auth/login", json={"role": role})).json()["token"]


async def test_profiles_listed_with_defaults():
    async with await _client() as c:
        admin = await _login(c, "admin")
        r = (await c.get("/llm-profiles", headers={"Authorization": f"Bearer {admin}"})).json()
        roles = {p["role"]: p for p in r["items"]}
        assert "pllm" in roles and "qllm" in roles
        assert roles["pllm"]["model"] and roles["qllm"]["model"]


async def test_admin_can_switch_model_non_admin_cannot():
    from app.config import settings
    async with await _client() as c:
        admin = await _login(c, "admin")
        # These tests share the LIVE DB, so mutating the qllm profile and not
        # restoring it corrupts every later test/run: the LLM base URL is DeepSeek,
        # so leaving a non-DeepSeek model (or a low max_tokens) makes the NEXT real
        # LLM call 400. Capture, mutate, then restore to the DeepSeek default.
        items = (await c.get("/llm-profiles", headers={"Authorization": f"Bearer {admin}"})).json()["items"]
        orig = {p["role"]: p for p in items}["qllm"]
        try:
            r = await c.patch("/llm-profiles/qllm", headers={"Authorization": f"Bearer {admin}"},
                              json={"model": "deepseek-v4-flash", "max_tokens": 800})
            assert r.status_code == 200 and r.json()["max_tokens"] == 800

            emp = await _login(c, "employee")
            r2 = await c.patch("/llm-profiles/qllm", headers={"Authorization": f"Bearer {emp}"},
                               json={"model": "x"})
            assert r2.status_code == 403
        finally:
            # self-heal: force the model back to the DeepSeek default regardless of
            # what it was before (a prior broken run may have left it corrupted).
            await c.patch("/llm-profiles/qllm", headers={"Authorization": f"Bearer {admin}"},
                          json={"model": settings.qllm_model, "max_tokens": orig["max_tokens"]})


async def test_resolver_falls_back_to_env_without_row():
    import uuid
    from app.db import SessionLocal
    from app.services.llm_config import resolve
    async with SessionLocal() as db:
        prof = await resolve(db, uuid.uuid4(), "pllm")  # unknown tenant → env default
    assert prof.model and prof.max_tokens > 0
