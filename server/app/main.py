"""FastAPI application entrypoint for agent-forge."""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import configure_logging

configure_logging()
log = logging.getLogger("agentforge")
access_log = logging.getLogger("agentforge.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = settings.validate_production()
    if problems:
        for p in problems:
            log.error("FATAL config: %s", p)
        raise RuntimeError("refusing to start: insecure production configuration — " + "; ".join(problems))
    log.info("agent-forge starting env=%s demo_login=%s", settings.app_env, settings.demo_login_enabled)
    yield
    log.info("agent-forge shutting down")


app = FastAPI(
    title="agent-forge API",
    version="0.1.0",
    description="CaMeL governance engine — sources, registry, plans, approvals, audit.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_logging(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        latency = int((time.monotonic() - started) * 1000)
        access_log.exception("request failed", extra={
            "request_id": rid, "method": request.method, "path": request.url.path, "latency_ms": latency})
        raise
    latency = int((time.monotonic() - started) * 1000)
    response.headers["x-request-id"] = rid
    access_log.info("%s %s %s %dms", request.method, request.url.path, response.status_code, latency,
                    extra={"request_id": rid, "method": request.method, "path": request.url.path,
                           "status": response.status_code, "latency_ms": latency})
    return response


def _include_routers() -> None:
    from app.api import health

    app.include_router(health.router, prefix="/api/v1")
    for modname, attr in [
        ("identity", "router"), ("sources", "router"), ("registry", "router"),
        ("approvals", "router"), ("chat", "router"), ("traces", "router"),
        ("executions", "router"), ("plugins", "router"),
    ]:
        try:
            mod = __import__(f"app.api.{modname}", fromlist=[attr])
            app.include_router(getattr(mod, attr), prefix="/api/v1")
        except ModuleNotFoundError:
            pass


_include_routers()


@app.get("/")
async def root() -> dict:
    return {"service": "agent-forge", "docs": "/docs", "health": "/api/v1/health"}
