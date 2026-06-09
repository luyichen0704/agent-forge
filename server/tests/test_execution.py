"""Regression tests for Batch 2 (execution semantics + session)."""
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models.audit import Trace
from app.models.chat import ChatSession, ExecutionPlan, PlanStep
from app.models.execution import ApprovalRequest
from app.models.identity import User

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t/api/v1", timeout=30)


async def _login(c, role):
    return (await c.post("/auth/login", json={"role": role})).json()["token"]


async def _approved_write_plan() -> uuid.UUID:
    """employee plan with one approved write step but no bound args → exec will fail."""
    async with SessionLocal() as db:
        emp = (await db.execute(select(User).where(User.email == "wei@company.com"))).scalar_one()
        sess = ChatSession(tenant_id=emp.tenant_id, user_id=emp.id, title="exec-test")
        db.add(sess); await db.flush()
        trace = Trace(tenant_id=emp.tenant_id, title="exec-test", actor_id=emp.id,
                      acting_role="employee", status="open")
        db.add(trace); await db.flush()
        plan = ExecutionPlan(session_id=sess.id, trace_id=trace.id, intent="加急退款", writes=1,
                             required_confirm_level="confirm", status="awaiting_confirm")
        db.add(plan); await db.flush()
        ar = ApprovalRequest(tenant_id=emp.tenant_id, trace_id=trace.id, target_type="plan_step",
                             target_id="refund.expedite", confirm_level="confirm", status="approved",
                             requested_by=emp.id, required_votes=1,
                             expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        db.add(ar); await db.flush()
        db.add(PlanStep(plan_id=plan.id, step_no=1, kind="write", op_key="refund.expedite",
                        label="加急", capability_in=["data"], capability_out="write",
                        approval_request_id=ar.id, status="planned", input_refs_json={}))
        await db.commit()
        return plan.id


async def test_executor_failure_is_not_masked_as_done():
    plan_id = await _approved_write_plan()
    async with await _client() as c:
        emp = await _login(c, "employee")
        r = (await c.post(f"/plans/{plan_id}/confirm", headers={"Authorization": f"Bearer {emp}"})).json()
        # write step had no bound args → executor not_found → must NOT be 'done'
        assert r["status"] == "partial_failed", r
        assert r["blocked"] is True


async def test_logout_revokes_only_current_token():
    async with await _client() as c:
        t1 = await _login(c, "employee")
        t2 = await _login(c, "employee")
        assert (await c.post("/auth/logout", headers={"Authorization": f"Bearer {t1}"})).status_code == 200
        # t1 dead, t2 still alive
        assert (await c.get("/me", headers={"Authorization": f"Bearer {t1}"})).status_code == 401
        assert (await c.get("/me", headers={"Authorization": f"Bearer {t2}"})).status_code == 200
