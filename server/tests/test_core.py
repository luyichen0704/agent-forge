"""Pure-logic unit tests (no DB / no LLM) — fast and deterministic."""
from app.policies.engine import Identity, StepCtx, evaluate_step
from app.services import audit
from app.services.capabilities import (
    Capability, merge_all, required_confirm, stricter_confirm,
)


# ---- capability lattice ----
def test_trusted_alone_is_trusted():
    assert Capability.of("trusted").is_trusted


def test_parsed_dominates_merge_no_laundering():
    merged = merge_all([Capability.of("trusted"), Capability.of("parsed")])
    assert "parsed" in merged.labels
    assert not merged.is_trusted  # parsing untrusted data cannot raise trust


def test_qllm_output_inherits_inputs():
    out = Capability.of("data").derive_parse()
    assert "data" in out.labels and "parsed" in out.labels
    assert out.dominant == "parsed"


# ---- confirm-level lattice ----
def test_stricter_confirm():
    assert stricter_confirm("auto", "dual") == "dual"
    assert stricter_confirm("confirm", "auto") == "confirm"


def test_parsed_args_escalate_mutation_to_confirm():
    lvl = required_confirm("mutation", "auto", Capability.of("parsed"), "low")
    assert lvl == "confirm"


def test_high_risk_forces_dual():
    lvl = required_confirm("mutation", "confirm", Capability.of("data"), "critical")
    assert lvl == "dual"


def test_query_never_confirms():
    assert required_confirm("query", "dual", Capability.of("parsed"), "critical") == "auto"


# ---- policy ----
def test_role_not_permitted_is_denied():
    ctx = StepCtx(op_key="hr.salary_set", op_kind="mutation", op_confirm="dual", risk="critical",
                  kwargs={}, arg_caps=Capability.of("data"), allowed_roles=["admin"])
    d = evaluate_step(Identity(user_id="u1", role="employee"), ctx)
    assert d.effect == "deny"


def test_customer_scope_injection():
    ctx = StepCtx(op_key="order.query", op_kind="query", op_confirm="auto", risk="low",
                  kwargs={}, arg_caps=Capability.of("trusted"),
                  allowed_roles=["customer", "employee", "admin"], permission_scope="self")
    d = evaluate_step(Identity(user_id="cust-1", role="customer"), ctx)
    assert d.effect == "allow"
    assert d.injected.get("user_id") == "cust-1"  # forced to caller


# ---- planner op_key hiding (domain-expert plain language) ----
def test_normalise_hides_raw_op_key_in_prose():
    from app.services.planner import _normalise
    draft = {
        "intent": "查询 staffUsers",
        "reasoning_summary": "直接使用 staffUsers 查询操作获取员工列表。",
        "steps": [{"step_no": 1, "kind": "query", "op_key": "staffUsers",
                   "label": "查询员工用户列表", "capability_out": "data", "args": {}}],
        "policy_hints": ["staffUsers 无需确认"],
    }
    out = _normalise(draft)
    assert "staffUsers" not in out["reasoning_summary"]
    assert "staffUsers" not in out["intent"]
    assert "staffUsers" not in out["policy_hints"][0]
    assert out["reasoning_summary"] == "直接使用 查询员工用户列表 查询操作获取员工列表。"


def test_normalise_op_key_replace_is_prefix_safe():
    # longest-first replacement: "users" must not partial-match inside another key
    from app.services.planner import _normalise
    draft = {"intent": "", "reasoning_summary": "users 与 user 操作", "policy_hints": [],
             "steps": [
                 {"step_no": 1, "kind": "query", "op_key": "users", "label": "查询用户",
                  "capability_out": "data", "args": {}},
                 {"step_no": 2, "kind": "query", "op_key": "user", "label": "单用户",
                  "capability_out": "data", "args": {}}]}
    out = _normalise(draft)
    assert out["reasoning_summary"] == "查询用户 与 单用户 操作"


# ---- audit hash chain ----
def test_hash_chain_detects_tamper():
    h1 = audit.compute_hash(1, "A", {"x": 1}, audit.GENESIS)
    h2 = audit.compute_hash(2, "B", {"y": 2}, h1)
    # tampering with event 1's payload changes its hash, breaking the link to h2
    h1_tampered = audit.compute_hash(1, "A", {"x": 999}, audit.GENESIS)
    assert h1 != h1_tampered
    assert audit.compute_hash(2, "B", {"y": 2}, h1_tampered) != h2
