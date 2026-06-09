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

from app.config import settings
from app.models.audit import LLMRun
from app.services.llm import llm

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
Only use op_key values present in the catalogue. Keep steps minimal and correct."""


async def plan(
    db: AsyncSession,
    trace_id: uuid.UUID,
    *,
    role: str,
    instruction: str,
    operations: list[dict],
) -> dict:
    catalogue = "\n".join(
        f"- {o['op_key']} ({o['kind']}, confirm={o['confirm_level']}, roles={o['roles']}): {o.get('desc','')}"
        for o in operations
    ) or "- (none available)"

    user = (
        f"Caller role: {role}\n"
        f"Available operations:\n{catalogue}\n\n"
        f"User instruction:\n{instruction}"
    )

    draft, result = await llm.structured(settings.pllm_model, SYSTEM, user, max_tokens=1600)
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
