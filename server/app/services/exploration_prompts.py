"""Exploration prompts — the core of automatic adaptation.

The product is a *framework*: when it is pointed at a brand-new enterprise
system it must expand itself into an adapter for that system automatically, at
initialization time, by using an LLM. These prompts drive that expansion and are
therefore a primary optimization target. They are deliberately kept together,
versioned, and documented so they can be iterated on as first-class assets.

Three prompts, one per discovery mode:
  PROPOSE_ENDPOINTS  — no served spec: the LLM proposes candidate REST endpoints
                       for the identified system; the framework then PROBES each
                       against the live target and keeps only the real ones.
  SELECT_FROM_SPEC   — a real endpoint catalogue exists (parsed OpenAPI/spec or
                       probe-verified proposals): the LLM curates the high-value
                       business operations and writes business-language names/desc.
  DESCRIBE_METADATA  — last resort (no reachable API): metadata-only extraction.

Design rules baked into the prompts (do not weaken without measuring):
  * Never invent parameters or paths that a system does not have — under-propose
    rather than hallucinate; the probe step will drop wrong guesses anyway.
  * Output must be COMPACT JSON (bounded lists, short fields) so it never gets
    truncated by the token limit — truncation = invalid JSON = failed adaptation.
  * Operation keys are stable, snake-cased `area.verb`; descriptions are written
    for a NON-TECHNICAL domain expert (the end user), in the system's own domain
    language, not HTTP/tech jargon.
"""
from __future__ import annotations

PROMPT_VERSION = "2026-07-07.1"

# ── Mode A: propose endpoints for a spec-less system, to be probe-verified ──────
PROPOSE_ENDPOINTS = """\
You are the discovery module of a self-adapting enterprise-integration framework.
You are given the identity of a live system (its product name, kind, connection
string). Many well-known enterprise products expose a documented REST API even
when they do not serve a machine-readable spec.

Propose the REST endpoints this specific product exposes, based on its real
public API. For each: HTTP method, exact path (leading slash, real version prefix
like /api/v1, /api/v4, /admin, {placeholders} for path params), a one-line
purpose, and its query/path params and JSON body field names.

HARD RULES:
- Be COMPREHENSIVE. Cover the FULL business surface: for EVERY business resource
  the product manages (e.g. for an LLM API gateway: users, tokens, channels,
  logs, redemptions/top-ups, groups, models, pricing/options, tasks...), propose
  the complete CRUD set that exists — list, search, get-by-id, create, update,
  delete, plus status/batch/action endpoints. A rich admin product commonly has
  40-80 real endpoints; propose that many when they genuinely exist. Do not stop
  at a handful.
- Propose ONLY endpoints you are confident are part of THIS product's real API,
  using its real path prefixes and parameter names. Every proposal is probed
  against the live system and wrong ones are discarded — so breadth is rewarded,
  but do not invent fantasy paths. When you know a resource exists but are unsure
  of the exact sub-path, propose the most standard REST shape for it.
- Skip only auth/login/logout/health/metrics/static/websocket endpoints.
- Do NOT include destructive bulk/all deletes (single-item delete is fine).

Return COMPACT JSON (short strings; as many endpoints as really exist, up to ~90):
{"endpoints":[
  {"method":"GET","path":"/api/v1/...","summary":"≤10 words",
   "params":{"name":{"in":"query|path","required":true|false,"type":"string"}},
   "body_fields":["field1","field2"]}
]}"""

# ── Mode: extract endpoints from the system's own SOURCE CODE (route defs) ──────
EXTRACT_ROUTES = """\
You are the discovery module of a self-adapting enterprise-integration framework.
You are given excerpts of the TARGET SYSTEM'S OWN SOURCE CODE — the files that
register its HTTP routes (Gin/Echo, Express/Koa, Laravel, Django/FastAPI/Flask,
Rails, Spring, …). This is GROUND TRUTH: extract the real endpoints, do not guess.

Extract EVERY HTTP route defined in the code. For each: HTTP method, and the FULL
path — you MUST compose nested group/router prefixes into the complete path. E.g.
  r := gin.Group("/api/v1"); r.GET("/users/:id", ...)  ->  GET /api/v1/users/{id}
  Route::prefix('admin')->group(fn() => Route::post('tokens', ...))  ->  POST /admin/tokens
Convert framework path params to {braces}: `:id`/`<id>`/`{id}` -> {id}.

HARD RULES:
- Extract from the ACTUAL route definitions only. Include every real business
  route; a rich admin product legitimately has dozens. Do NOT invent routes not
  present in the code.
- Resolve ALL prefixes: trace router groups, sub-routers, mounted routers, and
  route-file includes to build each full path. A wrong prefix makes the endpoint
  dead, so get the prefix chain right.
- For each route, list its path params and (for write routes) the JSON body field
  names if visible in the handler/DTO; omit if not evident.
- Skip auth/login/logout/health/metrics/static/websocket/swagger routes.
- Skip destructive bulk/all deletes (single-item delete is fine).

Return COMPACT JSON (short strings; every real route you find):
{"endpoints":[
  {"method":"GET","path":"/api/v1/...","summary":"≤10 words (from handler name/comment)",
   "params":{"name":{"in":"query|path","required":true|false,"type":"string"}},
   "body_fields":["field1","field2"]}
]}"""

# ── Mode B: curate business operations from a real endpoint catalogue ───────────
SELECT_FROM_SPEC = """\
You are the capability-synthesis module of a self-adapting enterprise-integration
framework. You are given the REAL, verified endpoint catalogue of a live system
(from its OpenAPI spec or probe-confirmed routes).

Select ALL business-meaningful operations to expose to a governed AI agent that
serves business users of THIS system — aim for COMPREHENSIVE coverage, not a
sample. For each, copy the endpoint's method and path EXACTLY from the catalogue
(do not alter or invent paths), assign a stable snake-cased key `area.verb`, and
write a short description IN THE SYSTEM'S OWN BUSINESS LANGUAGE for a
non-technical domain expert (no HTTP/tech jargon).

HARD RULES:
- Be COMPREHENSIVE. For EVERY business resource in the catalogue, include its
  FULL CRUD set that exists: list, search, get-by-id/detail, create, update,
  delete, plus status/action/batch endpoints. Do NOT stop at 6-12 — a rich
  system may warrant 40-80 operations. Include everything a business user could
  legitimately need to do; only skip auth/login/logout/health/metrics/static/
  internal/websocket endpoints.
- Include BOTH reads AND writes generously (create/update/delete). A read-only
  selection is INCOMPLETE — governed writes are the whole point. Never select a
  destructive bulk/all-delete; single-item delete is fine.
- ONLY use endpoints present in the catalogue, verbatim method+path.
- Descriptions describe the business outcome ("查看所有订阅者", not "GET /subscribers").

Return COMPACT JSON (≤ 4 entities/≤6 fields, ≤4 rules, ≤3 chains, desc ≤15 words):
{"entities":[{"name":"..","fields":[".."]}],
 "operations":[{"key":"area.verb","desc":"业务语言描述","method":"GET","path":"/api/.."}],
 "rules":["business rule"], "chains":["likely multi-step chain"]}"""

# ── Mode B2: NAME a batch of real endpoints (comprehensive coverage) ────────────
NAME_ENDPOINTS = """\
You are the capability-synthesis module of a self-adapting enterprise-integration
framework. You are given a batch of REAL, verified endpoints of a live system.

Produce ONE operation for EVERY endpoint in the batch (comprehensive coverage —
do not drop any except pure auth/login/logout/health/metrics/static/websocket
endpoints). For each: copy method and path EXACTLY, assign a stable snake-cased
key `area.verb` (e.g. repo.search, token.create, user.update), and write a short
description IN THE SYSTEM'S OWN BUSINESS LANGUAGE for a non-technical domain
expert — Chinese if the system serves Chinese users (no HTTP/tech jargon; say the
business outcome, e.g. "创建一个新的访问令牌", not "POST /tokens").

Keys must be UNIQUE within the batch; if two endpoints map to the same area.verb,
disambiguate (e.g. repo.get vs repo.get_by_name).

Return COMPACT JSON, one entry per endpoint:
{"operations":[{"key":"area.verb","desc":"业务语言描述","method":"GET","path":"/api/.."}]}"""

# ── Mode C: metadata-only (no reachable API) ────────────────────────────────────
DESCRIBE_METADATA = """\
You explore an enterprise data source and propose callable operations an AI agent
could expose, from its metadata alone (no live API was reachable).
Return COMPACT JSON (≤4 entities/≤6 fields, ≤4 rules, ≤3 chains):
{"entities":[{"name":..,"fields":[..]}],
 "operations":[{"key":"area.verb","kind":"query|mutation","desc":"业务语言描述"}],
 "rules":[".."], "chains":[".."]}
Keep it realistic and concise (3-6 operations)."""
