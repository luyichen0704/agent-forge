"""Health + LLM connectivity probe."""
from fastapi import APIRouter

from app.config import settings
from app.services.llm import LLMError, explorer_llm, llm

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


@router.get("/health/llm")
async def health_llm() -> dict:
    """Verify the planning gateway (camel-hub) and the Explorer LLM answer."""
    out: dict = {"base_url": settings.llm_base_url,
                 "explorer_base_url": settings.explorer_base_url}
    checks = [("pllm", llm, settings.pllm_model), ("qllm", llm, settings.qllm_model),
              ("explorer", explorer_llm, settings.explorer_model or settings.pllm_model)]
    for role, client, model in checks:
        try:
            res = await client.chat(
                model, [{"role": "user", "content": "reply with exactly: PONG"}],
            )
            out[role] = {"model": model, "ok": "PONG" in res.content.upper(), "latency_ms": res.latency_ms}
        except LLMError as exc:
            out[role] = {"model": model, "ok": False, "error": str(exc)}
    return out
