"""Seed real rows into the database — this replaces the old frontend data.ts.

Run:  uv run python -m app.seed
Idempotent: clears the tenant's domain rows and re-inserts a coherent demo
dataset (a real org with customer/employee/admin users, an Operation Registry
with ABAC permissions, data sources, plugins, business records, and one
fully-formed trace so Flow/Audit have genuine data).
"""
from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.services.security import hash_password

from app.db import SessionLocal
from app.models import (
    ApprovalRequest, ApprovalVote, AuditEvent, BizRecord, ChatMessage, ChatSession,
    DataSource, DataflowEdge, DataflowNode, DiscoveredChain, DiscoveredEntity,
    DiscoveredOperation, DiscoveredRule, Execution, ExecutionPlan, ExplorationEvent,
    ExplorationJob, LLMRun, Operation, OperationPermission, Plugin, PluginRegistration,
    PlanStep, Role, Session, Tenant, Trace, User, UserRole,
)
from app.services import audit

TENANT_SLUG = "demo"

ROLES = [("customer", "客户", 0), ("employee", "员工", 1), ("admin", "管理员", 2)]

USERS = [
    ("zhang@demo.com", "张伟", "customer"),
    ("wei@company.com", "员工小卫", "employee"),
    ("admin@company.com", "管理员", "admin"),
]

# op_key, kind, confirm, risk, status, executor, role->scope grants
OPERATIONS = [
    ("order.query",     "query",    "auto",    "low",  "active",  "FunctionExecutor",
     [("customer", "self"), ("employee", None), ("admin", None)]),
    ("customer.query",  "query",    "auto",    "low",  "active",  "FunctionExecutor",
     [("employee", None), ("admin", None)]),
    ("order.cancel",    "mutation", "confirm", "high", "pending", "FunctionExecutor",
     [("employee", None), ("admin", None)]),
    ("refund.expedite", "mutation", "confirm", "high", "pending", "FunctionExecutor",
     [("customer", "self"), ("employee", None), ("admin", None)]),
    ("user.ban",        "mutation", "confirm", "high", "pending", "FunctionExecutor",
     [("admin", None)]),
    ("hr.salary_set",   "mutation", "dual",    "critical", "pending", "FunctionExecutor",
     [("admin", None)]),
]

DATA_SOURCES = [
    ("code",  "源代码",   "CodeExplorer",       "GitHub · company/backend",  "connected"),
    ("db",    "数据库",   "DatabaseExplorer",   "PostgreSQL · prod-db",      "connected"),
    ("api",   "API",      "APIExplorer",        "OpenAPI · /api/v1/docs",    "connected"),
    ("admin", "管理后台", "AdminPanelExplorer", "admin.company.com",         "running"),
    ("doc",   "文档",     "DocExplorer",        "Confluence · Engineering",  "connected"),
]

PLUGINS = [
    ("Explorer", "数据源探索", "compass",
     "class Explorer(ABC):\n  async def explore(self, src) -> list[OperationDraft]",
     [("CodeExplorer", "ok"), ("DatabaseExplorer", "ok"), ("APIExplorer", "ok"),
      ("AdminPanelExplorer", "wait"), ("DocExplorer", "ok")]),
    ("Executor", "执行后端 · 按优先级 fallback", "bolt",
     "class Executor(ABC):\n  async def execute(op, params)\n  async def rollback(exec_id)",
     [("APIExecutor", "ok"), ("FunctionExecutor", "ok"), ("SQLExecutor", "wait"), ("RPAExecutor", "wait")]),
    ("PolicyEngine", "策略判定", "shield",
     "class PolicyEngine(ABC):\n  def evaluate(identity, op, kwargs, dataflow) -> Decision",
     [("PythonPolicyEngine", "ok"), ("OPAPolicyEngine", "off"), ("CasbinPolicyEngine", "off")]),
    ("AuditSink", "审计后端", "doc",
     "class AuditSink(ABC):\n  async def write(record)\n  async def query(range)",
     [("PostgresAuditSink", "ok"), ("S3AuditSink", "ok"), ("ElasticAuditSink", "off")]),
    ("LLMAdapter", "模型接入", "code",
     "class LLMAdapter(ABC):\n  def chat(msgs)\n  def structured_output(schema)",
     [("AnthropicAdapter · P-LLM", "ok"), ("LocalQwen · Q-LLM", "ok"), ("OpenAIAdapter", "off")]),
]


async def run() -> None:
    async with SessionLocal() as db:
        # ---- tenant ----
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == TENANT_SLUG))).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name="Demo 企业", slug=TENANT_SLUG)
            db.add(tenant)
            await db.flush()
        tid = tenant.id

        # ---- wipe domain rows for a clean reseed ----
        for model in (AuditEvent, DataflowEdge, DataflowNode, Execution, ChatMessage, PlanStep,
                      ExecutionPlan, LLMRun, ApprovalVote, ApprovalRequest, ChatSession, Trace,
                      BizRecord, PluginRegistration, Plugin, OperationPermission, Operation,
                      ExplorationEvent, DiscoveredOperation, DiscoveredEntity, DiscoveredRule,
                      DiscoveredChain, ExplorationJob, DataSource):
            await db.execute(delete(model))
        await db.execute(delete(Session))
        await db.execute(delete(UserRole))
        await db.flush()

        # ---- roles ----
        roles: dict[str, Role] = {}
        for key, label, rank in ROLES:
            r = (await db.execute(select(Role).where(Role.tenant_id == tid, Role.key == key))).scalar_one_or_none()
            if r is None:
                r = Role(tenant_id=tid, key=key, label=label, rank=rank)
                db.add(r)
            roles[key] = r
        await db.flush()

        # ---- users ----
        users: dict[str, User] = {}
        for email, name, role_key in USERS:
            u = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if u is None:
                u = User(tenant_id=tid, email=email, display_name=name,
                         password_hash=hash_password("demo1234"))
                db.add(u)
                await db.flush()
            db.add(UserRole(user_id=u.id, role_id=roles[role_key].id))
            users[role_key] = u
        await db.flush()

        # ---- operations + permissions ----
        for op_key, kind, confirm, risk, status, executor, grants in OPERATIONS:
            op = Operation(
                tenant_id=tid, op_key=op_key, version=1, kind=kind, confirm_level=confirm,
                risk_level=risk, status=status, executor_binding=executor,
                rollback_binding=executor, policy_ref=f"{op_key.replace('.', '_')}_policy",
                published_at=datetime.now(timezone.utc) if status == "active" else None,
            )
            db.add(op)
            await db.flush()
            for role_key, scope in grants:
                db.add(OperationPermission(
                    operation_id=op.id, subject_type="role", subject_id=role_key,
                    effect="allow", condition_json={"scope": scope} if scope else {},
                ))

        # ---- data sources ----
        for typ, name, kind, conn, status in DATA_SOURCES:
            db.add(DataSource(tenant_id=tid, type=typ, name=name, connector_kind=kind,
                              conn=conn, status=status,
                              config_json={"progress": 45} if status == "running" else {}))

        # ---- plugins ----
        for iface, sub, icon, sig, impls in PLUGINS:
            p = Plugin(tenant_id=tid, iface=iface, sub=sub, icon=icon, code_signature=sig)
            db.add(p)
            await db.flush()
            for impl_name, st in impls:
                db.add(PluginRegistration(plugin_id=p.id, impl_name=impl_name, status=st,
                                          health="ok" if st == "ok" else "unknown"))

        # ---- business records (real state the executors mutate) ----
        db.add(BizRecord(tenant_id=tid, kind="refund", key="#3901", owner_user_id=users["customer"].id,
                         state_json={"amount": 299, "refund_status": "pending", "customer": "张伟"}))
        db.add(BizRecord(tenant_id=tid, kind="order", key="#3901", owner_user_id=users["customer"].id,
                         state_json={"amount": 299, "status": "shipped", "customer": "张伟"}))
        await db.flush()

        # ---- one fully-formed historical trace (Flow/Audit have real data) ----
        await _seed_demo_trace(db, tid, users["employee"])

        await db.commit()
        print(f"seeded tenant={tenant.slug} users={len(users)} ops={len(OPERATIONS)} "
              f"sources={len(DATA_SOURCES)} plugins={len(PLUGINS)}")


async def _seed_demo_trace(db, tid, employee) -> None:
    trace = Trace(tenant_id=tid, title="张伟退款加急", actor_id=employee.id,
                  acting_role="employee", status="closed")
    db.add(trace)
    await db.flush()

    steps = [
        ("n0", 'user_input("张伟")', ["trusted"], "user", "可信通道"),
        ("n1", "customer_query → customer", ["data"], "query", "customer.query"),
        ("n2", "order_query → orders", ["data"], "query", "order.query"),
        ("n3", "Q-LLM → refund_orders", ["parsed"], "parse", "Q-LLM (无放宽)"),
        ("n4", "expedite_refund → result", ["write"], "write", "refund.expedite"),
    ]
    for nid, label, caps, kind, via in steps:
        db.add(DataflowNode(trace_id=trace.id, node_id=nid, label=label, capability_set=caps,
                            source_kind=kind, readers="emp, admin", via=via))
    for a, b, k in [("n0", "n1", "query"), ("n1", "n2", "query"), ("n2", "n3", "parse"), ("n3", "n4", "write")]:
        db.add(DataflowEdge(trace_id=trace.id, from_node_id=a, to_node_id=b, transform_kind=k))

    db.add(Execution(trace_id=trace.id, op_key="refund.expedite", executor="FunctionExecutor",
                     status="ok", before_state={"refund_status": "pending", "amount": 299},
                     after_state={"refund_status": "expedited", "amount": 299},
                     idempotency_key="seed:1", latency_ms=142))
    await db.flush()

    for et, payload, cap in [
        ("REQUEST_RECEIVED", {"role": "employee", "instruction": "张伟退款加急"}, "data"),
        ("PLAN_GENERATED", {"steps": 5}, "data"),
        ("POLICY_EVALUATED", {"op": "refund.expedite", "decision": "allow"}, "trusted"),
        ("CONFIRMATION_REQUESTED", {"level": "confirm", "writes": 1}, "parsed"),
        ("USER_CONFIRMED", {"approver": "员工小卫"}, "trusted"),
        ("OPERATION_EXECUTED", {"op": "refund.expedite", "latency_ms": 142}, "write"),
        ("DATAFLOW_SNAPSHOT", {"nodes": 5, "edges": 4}, "data"),
        ("RESPONSE_SENT", {"tokens": 1200}, "data"),
    ]:
        await audit.append_event(db, trace.id, et, payload, cap=cap, actor_id=employee.id)


if __name__ == "__main__":
    asyncio.run(run())
