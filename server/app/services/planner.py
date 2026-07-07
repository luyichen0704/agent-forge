"""P-LLM planner — privileged, but never sees raw data.

Given the user's instruction, their identity, and the *catalogue* of available
operations, it emits a strict `PlanDraft` (JSON). It only reasons over operation
signatures and its own plan; concrete record values are resolved later by the
executor / Q-LLM. Output is validated and persisted with an `llm_runs` row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import LLMRun
from app.services.llm import llm
from app.services.llm_config import resolve as resolve_profile

_VALID_KINDS = {"query", "parse", "write"}
_VALID_CAPS = {"trusted", "data", "parsed", "write"}

SYSTEM = """\
You are the P-LLM (privileged planner) of a CaMeL-style governed agent.
You DECOMPOSE a user's natural-language instruction into an ordered plan of
operations chosen ONLY from the provided catalogue. You never see raw business
data — you only reference operation keys and parameter names.

Capability rules you must respect:
- A `query` step that reads internal data produces capability "data".
- A `parse` step (delegated to the quarantined Q-LLM) produces "parsed" and may
  never produce "trusted".
- A `write` step (mutation) produces "write" and ALWAYS needs confirmation.

Return JSON with this exact shape:
{
  "intent": "<one sentence>",
  "reasoning_summary": "<2-3 sentences, no raw data>",
  "writes": <int count of write steps>,
  "required_confirm_level": "auto|confirm|dual",
  "steps": [
    {"step_no": 1, "kind": "query|parse|write", "op_key": "<key or null>",
     "label": "<short human label>", "capability_out": "trusted|data|parsed|write",
     "args": {"<param>": "<literal or $ref>"}}
  ],
  "policy_hints": ["<short hint>", ...]
}
Only use op_key values present in the catalogue. Keep steps minimal and correct.
All natural-language fields you write — intent, reasoning_summary, every step
label, and policy_hints — MUST be in the SAME LANGUAGE as the user's instruction
(Chinese if the instruction is Chinese). Never write these in English for a
Chinese user; op_key values stay as given."""


async def plan(
    db: AsyncSession,
    trace_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID,
    role: str,
    instruction: str,
    operations: list[dict],
) -> dict:
    def _line(o: dict) -> str:
        line = f"- {o['op_key']} ({o['kind']}, confirm={o['confirm_level']}, roles={o['roles']}): {o.get('desc', '')}"
        if o.get("sig"):
            line += f" | args: {o['sig']}"
        if o.get("body"):
            line += f" | body: {o['body']}"
        return line

    catalogue = "\n".join(_line(o) for o in operations) or "- (none available)"

    user = (
        f"Caller role: {role}\n"
        f"Available operations:\n{catalogue}\n\n"
        f"User instruction:\n{instruction}"
    )

    prof = await resolve_profile(db, tenant_id, "pllm")
    draft, result = await llm.structured(prof.model, SYSTEM, user,
                                         temperature=prof.temperature)
    draft = _normalise(draft)

    run = LLMRun(
        trace_id=trace_id,
        llm_role="pllm",
        model=result.model,
        input_ref={"role": role, "instruction": instruction, "op_count": len(operations)},
        output_json=draft,
        token_usage=result.usage,
        latency_ms=result.latency_ms,
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()
    draft["_llm_run_id"] = str(run.id)
    return draft


def _normalise(draft: dict) -> dict:
    steps = []
    for i, s in enumerate(draft.get("steps", []), start=1):
        kind = s.get("kind") if s.get("kind") in _VALID_KINDS else "query"
        cap = s.get("capability_out")
        if cap not in _VALID_CAPS:
            cap = {"query": "data", "parse": "parsed", "write": "write"}[kind]
        args = s.get("args") if isinstance(s.get("args"), dict) else {}
        steps.append({
            "step_no": s.get("step_no", i),
            "kind": kind,
            "op_key": s.get("op_key"),
            "label": str(s.get("label", "")).strip()[:200] or kind,
            "capability_out": cap,
            "args": args,
        })
    writes = sum(1 for s in steps if s["kind"] == "write")
    confirm = draft.get("required_confirm_level")
    if confirm not in {"auto", "confirm", "dual"}:
        confirm = "confirm" if writes else "auto"
    return {
        "intent": str(draft.get("intent", "")).strip()[:300],
        "reasoning_summary": str(draft.get("reasoning_summary", "")).strip()[:600],
        "writes": writes,
        "required_confirm_level": confirm,
        "steps": steps,
        "policy_hints": [str(h)[:120] for h in draft.get("policy_hints", [])][:6],
    }
