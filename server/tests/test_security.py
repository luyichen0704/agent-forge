"""Regression tests for the IDOR / auth holes Codex reproduced (Batch 1).

In-process (httpx ASGITransport) against the real seeded DB; sets up rows
directly so no LLM call is needed.
"""
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models.audit import Trace
from app.models.chat import ChatSession, ExecutionPlan
from app.models.identity import User
from app.models.registry import Operation

# all async tests share one event loop so the global async engine pool stays valid
pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t/api/v1", timeout=30)


async def _login(c, role):
    r = await c.post("/auth/login", json={"role": role})
    return r.json()["token"]


async def _seed_employee_plan() -> tuple[uuid.UUID, uuid.UUID]:
    """Create an employee-owned session+trace+plan directly (no LLM)."""
    async with SessionLocal() as db:
        emp = (await db.execute(select(User).where(User.email == "wei@company.com"))).scalar_one()
        sess = ChatSession(tenant_id=emp.tenant_id, user_id=emp.id, title="sec-test")
        db.add(sess); await db.flush()
        trace = Trace(tenant_id=emp.tenant_id, title="sec-test trace", actor_id=emp.id,
                      acting_role="employee", status="open")
        db.add(trace); await db.flush()
        plan = ExecutionPlan(session_id=sess.id, trace_id=trace.id, intent="x", writes=1,
                             required_confirm_level="confirm", status="awaiting_confirm")
        db.add(plan); await db.commit()
        return plan.id, trace.id


async def test_customer_cannot_read_or_confirm_others_plan():
    plan_id, trace_id = await _seed_employee_plan()
    async with await _client() as c:
        cust = await _login(c, "customer")
        H = {"Authorization": f"Bearer {cust}"}
        assert (await c.get(f"/plans/{plan_id}", headers=H)).status_code == 404
        assert (await c.post(f"/plans/{plan_id}/confirm", headers=H)).status_code == 404
        assert (await c.post(f"/plans/{plan_id}/cancel", headers=H)).status_code == 404


async def test_customer_cannot_read_others_trace_audit():
    _, trace_id = await _seed_employee_plan()
    async with await _client() as c:
        cust = await _login(c, "customer")
        H = {"Authorization": f"Bearer {cust}"}
        assert (await c.get(f"/traces/{trace_id}/audit", headers=H)).status_code == 404
        assert (await c.get(f"/traces/{trace_id}/flow", headers=H)).status_code == 404


async def test_sse_requires_auth():
    async with await _client() as c:
        r = await c.get(f"/exploration-jobs/{uuid.uuid4()}/events")
        assert r.status_code == 401  # no token → rejected before streaming


async def test_owner_can_still_read_own_plan():
    plan_id, _ = await _seed_employee_plan()
    async with await _client() as c:
        emp = await _login(c, "employee")
        r = await c.get(f"/plans/{plan_id}", headers={"Authorization": f"Bearer {emp}"})
        assert r.status_code == 200


async def test_customer_cannot_read_admin_only_operation():
    async with SessionLocal() as db:
        op = (await db.execute(select(Operation).where(Operation.op_key == "hr.salary_set"))).scalar_one()
        op_id = op.id
    async with await _client() as c:
        cust = await _login(c, "customer")
        r = await c.get(f"/operations/{op_id}", headers={"Authorization": f"Bearer {cust}"})
        assert r.status_code == 404
