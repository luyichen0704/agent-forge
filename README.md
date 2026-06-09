# agent-forge

> Workbench to **forge and govern enterprise AI agents** — explore your systems, generate capability-scoped operations, visualize dataflow, and audit every action.

`agent-forge` is a full-stack console for building safe, business-facing AI agents on top of the **CaMeL dual-LLM pattern**: a **P-LLM** (privileged planner) decomposes a request into a plan over a catalogue of operations, a **Q-LLM** (quarantined parser) handles untrusted data in isolation, every value carries a **security capability** (`trusted`/`data`/`parsed`/`write`), write operations pass a **policy engine** and **human approval**, and every action is recorded in a **tamper-evident audit hash-chain**.

This is a working system backed by a real database and a real LLM gateway — **no mock data**.

## Architecture

```
React + TS + Tailwind (Vite)            FastAPI + SQLAlchemy 2 + Postgres + Redis
┌───────────────────────────┐  /api/v1  ┌──────────────────────────────────────┐
│ 7 screens · react-query   │ ───────►  │ identity · sources · registry · chat   │
│ Explore Live Chat Flow    │  (proxy)  │ approvals · traces · executions · plugins│
│ Ops Audit Plugins         │           │                                        │
└───────────────────────────┘           │ CaMeL engine:                          │
                                         │  planner(P-LLM) · qparser(Q-LLM)       │
                                         │  capability lattice · policy engine    │
                                         │  executor registry · audit hash-chain  │
                                         └───────────────┬────────────────────────┘
                                                         │ OpenAI-compatible
                                                         ▼  api.camel-hub.com
                                              P-LLM claude-sonnet-4-5
                                              Q-LLM claude-haiku-4-5
```

Backend bounded contexts: `identity / sources / registry / chat-plans / executions-approvals / audit-traces` (see `server/app/`).

## Quick install (visual wizard)

No commands to memorize — run one script and click through a web page:

```bash
python3 installer/install.py     # opens http://127.0.0.1:8800
```

The wizard detects your toolchain (uv/docker/npm), lets you fill config and **pull the gateway's live model list** to pick P-LLM/Q-LLM, then one-click runs the whole bring-up (Postgres+Redis → deps → migrations → seed → admin password → API + Arq worker) with a live log and a health check. (Stdlib-only; nothing to `pip install`.)

## Run it (manual)

**1. Backend** (Postgres + Redis via Docker, FastAPI via uv):

```bash
cd server
cp .env.example .env          # set LLM_API_KEY (camel-hub) — see below
docker compose up -d          # postgres:5544, redis:6390
uv sync
uv run alembic upgrade head   # create schema
uv run python -m app.seed     # seed a real demo org (replaces old mock fixtures)
uv run uvicorn app.main:app --port 8099
```

Verify: `GET http://localhost:8099/api/v1/health/llm` should report both models OK.

**2. Frontend** (Vite dev server, proxies `/api` → `:8099`):

```bash
npm install
npm run dev                   # http://localhost:5173
```

Log in by role (customer / employee / admin) to see server-enforced RBAC differences. Demo users: `admin@company.com` / `wei@company.com` / `zhang@demo.com` (password `demo1234`).

> **Production deployment** (systemd or docker compose, TLS, real auth, logging, permissions, model-config & secrets storage): see **[DEPLOY.md](DEPLOY.md)**.

## Screens

| Screen | Backed by |
| --- | --- |
| **Explore** | `GET /sources`, `POST /sources/:id/explore` (LLM-driven discovery → registry) |
| **Live** | exploration job + SSE event stream (`/exploration-jobs/:id/events`) |
| **Chat** | sessions/messages → P-LLM `PlanDraft` → policy → confirm/execute |
| **Flow** | `GET /traces/:id/flow` — capability-annotated dataflow graph |
| **Ops** | `GET /operations` — versioned registry, publish/disable (RBAC) |
| **Audit** | `GET /traces/:id/audit` — hash-chain with integrity verification + rollback |
| **Plugins** | `GET /plugins` — pluggable interface contracts |

## Stack

**Frontend** React 18 · TypeScript · Vite 5 · Tailwind 3 · @tanstack/react-query · Vitest.
**Backend** Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL · Redis · SSE · httpx.

## Tests

```bash
npm run test                         # frontend (vitest)
cd server && uv run pytest           # backend pure-logic unit tests
cd server && uv run python -m tests.smoke   # in-process end-to-end (real DB + real LLM)
```

## Security model (why this isn't just a chatbot)

- **RBAC is server-enforced**: the API only returns data/operations the caller's role may use — the frontend never receives unauthorized data.
- **Capabilities don't launder**: Q-LLM output inherits its inputs' provenance and is never `trusted`, so adversarial data can't escalate.
- **Writes are gated**: mutations require confirmation; high-risk ones require **dual approval** (two distinct admins, enforced by a unique vote constraint).
- **Everything is auditable**: each trace is an append-only SHA-256 hash-chain; `GET /traces/:id/audit` re-verifies the chain and reports any break.
