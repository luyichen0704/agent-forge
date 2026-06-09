"""Batch 3: the real CaMeL chain executes (query→Q-LLM→write) and dual approval
requires two distinct admins. Uses the real DB + real Q-LLM (parse step)."""
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models.audit import Trace
from app.models.business import BizRecord
from app.models.chat import ChatSession, ExecutionPlan, PlanStep
from app.models.execution import ApprovalRequest
from app.models.identity import Role, Session, User, UserRole
from app.services.security import new_token

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t/api/v1", timeout=60)


async def _token_for(email: str) -> str:
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.email == email))).scalar_one()
        roles = (await db.execute(
            select(Role.key).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == u.id)
        )).scalars().all()
        tok = new_token()
        db.add(Session(user_id=u.id, token=tok, acting_role=roles[0],
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        await db.commit()
        return tok


async def _build_chain_plan(write_op: str, *, confirm_level: str, requester_email: str,
                            with_approval: bool):
    async with SessionLocal() as db:
        emp = (await db.execute(select(User).where(User.email == requester_email))).scalar_one()
        # reset the business record so the assertion is meaningful
        rec = (await db.execute(select(BizRecord).where(
            BizRecord.kind == "refund", BizRecord.key == "#3901"))).scalar_one()
        rec.state_json = {**rec.state_json, "refund_status": "pending"}
        sess = ChatSession(tenant_id=emp.tenant_id, user_id=emp.id, title="chain-test")
        db.add(sess); await db.flush()
        trace = Trace(tenant_id=emp.tenant_id, title="chain-test", actor_id=emp.id,
                      acting_role="employee", status="open")
        db.add(trace); await db.flush()
        plan = ExecutionPlan(session_id=sess.id, trace_id=trace.id, intent="加急张伟 pending 退款",
                             writes=1, required_confirm_level=confirm_level, status="awaiting_confirm")
        db.add(plan); await db.flush()
        ar_id = None
        if with_approval:
            ar = ApprovalRequest(tenant_id=emp.tenant_id, trace_id=trace.id, target_type="plan_step",
                                 target_id=write_op, confirm_level="dual", status="pending",
                                 requested_by=emp.id, required_votes=2,
                                 expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
            db.add(ar); await db.flush(); ar_id = ar.id
        db.add(PlanStep(plan_id=plan.id, step_no=1, kind="query", op_key="order.query",
                        label="查询张伟订单", capability_in=["trusted"], capability_out="data",
                        status="planned", input_refs_json={}))
        db.add(PlanStep(plan_id=plan.id, step_no=2, kind="parse", op_key=None,
                        label="筛选 refund_status 为 pending 的退款订单", capability_in=["data"],
                        capability_out="parsed", status="planned", input_refs_json={}))
        db.add(PlanStep(plan_id=plan.id, step_no=3, kind="write", op_key=write_op,
                        label="加急退款", capability_in=["parsed"], capability_out="write",
                        approval_request_id=ar_id, status="planned", input_refs_json={}))
        await db.commit()
        return plan.id, ar_id


async def _refund_status() -> str:
    async with SessionLocal() as db:
        rec = (await db.execute(select(BizRecord).where(
            BizRecord.kind == "refund", BizRecord.key == "#3901"))).scalar_one()
        return rec.state_json.get("refund_status")


async def test_real_chain_reads_parses_and_writes_bizrecords():
    plan_id, _ = await _build_chain_plan("refund.expedite", confirm_level="confirm",
                                         requester_email="wei@company.com", with_approval=False)
    assert await _refund_status() == "pending"
    async with await _client() as c:
        emp = await _token_for("wei@company.com")
        r = (await c.post(f"/plans/{plan_id}/confirm", headers={"Authorization": f"Bearer {emp}"})).json()
        assert r["status"] == "done", r
    # the write actually mutated the real business row
    assert await _refund_status() == "expedited"
    # audit chain recorded the real chain and still verifies
    async with await _client() as c:
        emp = await _token_for("wei@company.com")
        plan = (await c.get(f"/plans/{plan_id}", headers={"Authorization": f"Bearer {emp}"})).json()
        au = (await c.get(f"/traces/{plan['trace_id']}/audit",
                          headers={"Authorization": f"Bearer {emp}"})).json()
    events = {e["event"] for e in au["events"]}
    assert {"DATA_READ", "QLLM_PARSED", "OPERATION_EXECUTED"} <= events, events
    assert au["verification"]["valid"] is True


async def test_dual_approval_needs_two_distinct_admins():
    plan_id, ar_id = await _build_chain_plan("refund.expedite", confirm_level="dual",
                                             requester_email="wei@company.com", with_approval=True)
    a1 = await _token_for("admin@company.com")
    a2 = await _token_for("admin2@company.com")
    async with await _client() as c:
        H1 = {"Authorization": f"Bearer {a1}"}
        # first admin vote → still pending (1/2)
        r1 = (await c.post(f"/approval-requests/{ar_id}/votes", headers=H1, json={"decision": "approve"})).json()
        assert r1["status"] == "pending" and r1["approve_votes"] == 1
        # same admin voting again → rejected
        assert (await c.post(f"/approval-requests/{ar_id}/votes", headers=H1,
                             json={"decision": "approve"})).status_code == 409
        # second DISTINCT admin → approved
        r2 = (await c.post(f"/approval-requests/{ar_id}/votes",
                           headers={"Authorization": f"Bearer {a2}"}, json={"decision": "approve"})).json()
        assert r2["status"] == "approved", r2
        # now the owner can confirm and it executes
        emp = await _token_for("wei@company.com")
        r = (await c.post(f"/plans/{plan_id}/confirm", headers={"Authorization": f"Bearer {emp}"})).json()
        assert r["status"] == "done", r
    assert await _refund_status() == "expedited"
