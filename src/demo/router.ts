/**
 * Demo router — maps [method, path] to mock handlers.
 * All handlers accept the demo state as first argument for test isolation.
 */

import { ApiError, getToken } from '../api/http';
import type { AuditEvent, ChatMessage, Execution, FlowEdge, FlowNode, LlmProfile, TraceSummary } from '../api/types';
import {
  buildScenarioAPlan, buildScenarioADonePlan,
  buildScenarioBPlan, buildScenarioCPlan,
  matchScenario,
} from './fixtures/chatScript';
import { DEMO_LLM_MODELS } from './fixtures/llm';
import { DEMO_PLUGINS } from './fixtures/plugins';
import { DEMO_USERS, buildMe } from './fixtures/users';
import { buildHashChain } from './hash';
import { sleepConfirm, sleepGet, sleepSend, sleepVote } from './pacing';
import type { DemoState, TraceData } from './state';
import { getDemoState, nextId } from './state';

// ────────────────────────────────────────────────
// Route table type
// ────────────────────────────────────────────────

type Handler = (state: DemoState, method: string, path: string, body: unknown) => Promise<unknown>;

interface Route {
  method: string;
  pattern: RegExp;
  handler: Handler;
}

const ROUTES: Route[] = [];

function route(method: string, pattern: RegExp, handler: Handler): void {
  ROUTES.push({ method, pattern, handler });
}

// ────────────────────────────────────────────────
// Auth
// ────────────────────────────────────────────────

route('POST', /^\/auth\/token$/, async (state, _m, _p, body) => {
  const { email, password } = body as { email: string; password: string };
  const user = DEMO_USERS.find(u => u.email === email);
  if (!user || user.password !== password) throw new ApiError(401, '邮箱或密码错误');
  const token = `demo-${user.id}-${Date.now()}`;
  state.tokens.set(token, user.id);
  state.currentUserId = user.id;
  return { token };
});

route('POST', /^\/auth\/login$/, async (state, _m, _p, body) => {
  // Legacy role-based login (used by useLogin)
  const { role } = body as { role: string };
  const user = DEMO_USERS.find(u => u.role === role) ?? DEMO_USERS[0];
  const token = `demo-${user.id}-${Date.now()}`;
  state.tokens.set(token, user.id);
  state.currentUserId = user.id;
  return { token };
});

route('POST', /^\/auth\/logout$/, async (state) => {
  state.currentUserId = null;
  return {};
});

// ────────────────────────────────────────────────
// /me
// ────────────────────────────────────────────────

route('GET', /^\/me$/, async (state) => {
  const user = getCurrentUser(state);
  return buildMe(user);
});

// ────────────────────────────────────────────────
// Operations
// ────────────────────────────────────────────────

route('GET', /^\/operations/, async (state) => {
  await sleepGet();
  return {
    items: state.operations,
    pending_count: state.operations.filter(o => o.status === 'pending').length,
    total: state.operations.length,
  };
});

route('POST', /^\/operations\/([^/]+)\/publish$/, async (state, _m, path) => {
  await sleepGet();
  const id = path.match(/\/operations\/([^/]+)\/publish$/)![1];
  const op = state.operations.find(o => o.id === id);
  if (!op) throw new ApiError(404, 'operation not found');
  op.status = 'active';
  return { ...op };
});

route('POST', /^\/operations\/([^/]+)\/disable$/, async (state, _m, path) => {
  await sleepGet();
  const id = path.match(/\/operations\/([^/]+)\/disable$/)![1];
  const op = state.operations.find(o => o.id === id);
  if (!op) throw new ApiError(404, 'operation not found');
  op.status = 'disabled';
  return { ...op };
});

// ────────────────────────────────────────────────
// Data sources
// ────────────────────────────────────────────────

route('GET', /^\/sources$/, async (state) => {
  await sleepGet();
  return { items: state.sources };
});

route('POST', /^\/sources\/([^/]+)\/explore$/, async (state, _m, path) => {
  await sleepGet();
  const sourceId = path.match(/\/sources\/([^/]+)\/explore$/)![1];
  const src = state.sources.find(s => s.id === sourceId);
  if (!src) throw new ApiError(404, 'source not found');
  const jobId = nextId(state, 'job');
  state.jobs.set(jobId, {
    id: jobId, source_id: sourceId,
    status: 'running', phase: 1, progress: 0,
  });
  return { job_id: jobId };
});

route('GET', /^\/exploration-jobs\/([^/]+)$/, async (state, _m, path) => {
  await sleepGet();
  const id = path.match(/\/exploration-jobs\/([^/]+)$/)![1];
  const job = state.jobs.get(id);
  if (!job) throw new ApiError(404, 'job not found');
  return { ...job };
});

// ────────────────────────────────────────────────
// Plugins
// ────────────────────────────────────────────────

route('GET', /^\/plugins$/, async () => {
  await sleepGet();
  return { items: DEMO_PLUGINS };
});

// ────────────────────────────────────────────────
// Traces
// ────────────────────────────────────────────────

route('GET', /^\/traces$/, async (state) => {
  await sleepGet();
  const items: TraceSummary[] = Array.from(state.traces.values())
    .map(t => t.summary)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  return { items };
});

route('GET', /^\/traces\/([^/]+)\/flow$/, async (state, _m, path) => {
  await sleepGet();
  const id = path.match(/\/traces\/([^/]+)\/flow$/)![1];
  const tr = getTrace(state, id);
  return { trace_id: id, nodes: tr.flowNodes, edges: tr.flowEdges };
});

route('GET', /^\/traces\/([^/]+)\/audit$/, async (state, _m, path) => {
  await sleepGet();
  const id = path.match(/\/traces\/([^/]+)\/audit$/)![1];
  const tr = getTrace(state, id);
  const events = tr.auditEvents;
  return {
    trace_id: id,
    verification: { valid: true, count: events.length, head: events[events.length - 1]?.hash },
    events,
  };
});

route('GET', /^\/traces\/([^/]+)\/executions$/, async (state, _m, path) => {
  await sleepGet();
  const id = path.match(/\/traces\/([^/]+)\/executions$/)![1];
  const tr = getTrace(state, id);
  return { items: tr.executions };
});

route('POST', /^\/executions\/([^/]+)\/rollback$/, async (state, _m, path) => {
  await sleepGet();
  const id = path.match(/\/executions\/([^/]+)\/rollback$/)![1];
  // Find execution in any trace and mark as rolled_back
  for (const tr of state.traces.values()) {
    const exec = tr.executions.find(e => e.id === id);
    if (exec) {
      exec.status = 'rolled_back';
      return {};
    }
  }
  throw new ApiError(404, 'execution not found');
});

// ────────────────────────────────────────────────
// Chat sessions
// ────────────────────────────────────────────────

route('GET', /^\/chat\/sessions$/, async (state) => {
  await sleepGet();
  const user = getCurrentUser(state);
  const sessions = Array.from(state.sessions.values())
    .filter(s => s.userId === user.id)
    .map(s => ({ id: s.id, title: s.title }));
  return { items: sessions };
});

route('POST', /^\/chat\/sessions$/, async (state) => {
  const user = getCurrentUser(state);
  const id = nextId(state, 'sess');
  const session = { id, userId: user.id, title: '新会话', messages: [] };
  state.sessions.set(id, session);
  return { id, title: '新会话' };
});

route('GET', /^\/chat\/sessions\/([^/]+)\/messages$/, async (state, _m, path) => {
  await sleepGet();
  const id = path.match(/\/chat\/sessions\/([^/]+)\/messages$/)![1];
  const session = state.sessions.get(id);
  if (!session) throw new ApiError(404, 'session not found');
  return { items: session.messages };
});

route('POST', /^\/chat\/sessions\/([^/]+)\/messages$/, async (state, _m, path, body) => {
  const id = path.match(/\/chat\/sessions\/([^/]+)\/messages$/)![1];
  const session = state.sessions.get(id);
  if (!session) throw new ApiError(404, 'session not found');

  const content = (body as { content: string }).content;
  const now = new Date().toISOString();

  // Update session title if first message
  if (session.title === '新会话') {
    session.title = content.slice(0, 40);
  }

  // Add user message
  const userMsg: ChatMessage = {
    id: nextId(state, 'msg'), role: 'user', content, created_at: now, plan: null,
  };
  session.messages.push(userMsg);

  await sleepSend();

  const scenario = matchScenario(content);
  const user = getCurrentUser(state);
  const traceId = nextId(state, 'tr');
  const planId = nextId(state, 'plan');

  let reply: string;
  let plan;

  if (scenario === 'A') {
    plan = buildScenarioAPlan(traceId, planId);
    reply = `我将执行以下操作，涉及 ${plan.writes} 个写操作，需要确认（${plan.required_confirm_level}）。`;
  } else if (scenario === 'B') {
    const approvalId = nextId(state, 'appr');
    plan = buildScenarioBPlan(traceId, planId, approvalId);
    reply = `我将执行以下操作，涉及 ${plan.writes} 个写操作，需要确认（${plan.required_confirm_level}）。`;
    // Create pending approval request
    state.approvals.push({
      id: approvalId,
      trace_id: traceId,
      target_type: 'plan',
      target_id: planId,
      confirm_level: 'dual',
      status: 'pending',
      required_votes: 2,
      approve_votes: 0,
      votes: [],
    });
    // Store plan in session for future confirm
    state.sessions.set(`plan:${planId}`, {
      id: planId, userId: user.id, title: 'B',
      messages: [{ id: approvalId, role: 'system', content: 'appr', created_at: now, plan }],
    });
  } else {
    // Scenario C / fallback — auto, direct done
    const intent = scenario === 'C' ? '查询订单信息' : `处理请求：${content.slice(0, 30)}`;
    plan = buildScenarioCPlan(traceId, planId, intent);
    reply = `已规划并执行：${plan.intent}`;
    // Materialize a simple trace for C
    materializeTraceC(state, traceId, user.id);
  }

  // Store plan reference in session
  (state.sessions.get(id) as { pendingPlanId?: string } & typeof session).pendingPlanId = planId;
  state.sessions.set(`plan:${planId}:state`, {
    id: planId, userId: user.id, title: scenario,
    messages: [{ id: traceId, role: 'system', content: scenario, created_at: now, plan: null }],
  });
  // Store plan object for confirm/cancel
  (state as unknown as Record<string, unknown>)[`plan:${planId}`] = plan;
  (state as unknown as Record<string, unknown>)[`plan:${planId}:traceId`] = traceId;

  const assistantMsg: ChatMessage = {
    id: nextId(state, 'msg'), role: 'assistant', content: reply, created_at: new Date().toISOString(), plan,
  };
  session.messages.push(assistantMsg);

  return { reply, plan };
});

// ────────────────────────────────────────────────
// Plans confirm/cancel
// ────────────────────────────────────────────────

route('POST', /^\/plans\/([^/]+)\/confirm$/, async (state, _m, path) => {
  const planId = path.match(/\/plans\/([^/]+)\/confirm$/)![1];
  const plan = (state as unknown as Record<string, unknown>)[`plan:${planId}`] as ReturnType<typeof buildScenarioAPlan> | undefined;
  if (!plan) throw new ApiError(404, 'plan not found');

  await sleepConfirm();

  const scenario = (state as unknown as Record<string, unknown>)[`plan:${planId}:traceId`] ? 'A' : 'unknown';
  const traceId = (state as unknown as Record<string, unknown>)[`plan:${planId}:traceId`] as string;

  // Mutate the stored plan in place: chat messages embed the same object
  // reference, so refetched messages must see the updated status.
  if (plan.required_confirm_level === 'dual') {
    // Scenario B — check if approval is complete
    const appr = state.approvals.find(a => a.target_id === planId);
    if (!appr || appr.approve_votes < appr.required_votes) {
      Object.assign(plan, { blocked: true });
      return { ...plan };
    }
    // Both votes in — approve
    Object.assign(plan, { status: 'done', blocked: false });
    return { ...plan };
  }

  // Scenario A
  Object.assign(plan, buildScenarioADonePlan(planId, traceId));
  // Materialize trace A
  materializeTraceA(state, traceId, getCurrentUser(state));
  return { ...plan };
});

route('POST', /^\/plans\/([^/]+)\/cancel$/, async (state, _m, path) => {
  const planId = path.match(/\/plans\/([^/]+)\/cancel$/)![1];
  const plan = (state as unknown as Record<string, unknown>)[`plan:${planId}`] as { id: string; status: string } | undefined;
  if (!plan) throw new ApiError(404, 'plan not found');
  plan.status = 'cancelled';
  return { id: plan.id, status: 'cancelled' };
});

// ────────────────────────────────────────────────
// Approval requests & votes
// ────────────────────────────────────────────────

route('GET', /^\/approval-requests/, async (state, _m, path) => {
  await sleepGet();
  const statusMatch = path.match(/status=([^&]+)/);
  const status = statusMatch ? statusMatch[1] : undefined;
  const items = status ? state.approvals.filter(a => a.status === status) : state.approvals;
  return { items };
});

route('POST', /^\/approval-requests\/([^/]+)\/votes$/, async (state, _m, path, body) => {
  await sleepVote();
  const id = path.match(/\/approval-requests\/([^/]+)\/votes$/)![1];
  const appr = state.approvals.find(a => a.id === id);
  if (!appr) throw new ApiError(404, 'approval request not found');

  const user = getCurrentUser(state);
  const { decision, comment } = body as { decision: string; comment?: string };

  // Check duplicate vote
  if (appr.votes.some(v => v.approver_id === user.id)) {
    throw new ApiError(409, '同一审批人不能重复投票');
  }

  const vote: import('../api/types').ApprovalVote = {
    approver_id: user.id,
    decision,
    comment: comment ?? '',
    created_at: new Date().toISOString(),
  };
  appr.votes.push(vote);

  if (decision === 'approve') appr.approve_votes++;

  if (appr.approve_votes >= appr.required_votes) {
    appr.status = 'approved';
    // Complete associated plan
    const plan = (state as unknown as Record<string, unknown>)[`plan:${appr.target_id}`] as { status?: string; blocked?: boolean } | undefined;
    if (plan) {
      plan.status = 'done';
      plan.blocked = false;
    }
  } else if (appr.votes.filter(v => v.decision === 'reject').length > 0) {
    appr.status = 'rejected';
  }

  return { ...appr };
});

// ────────────────────────────────────────────────
// LLM profiles
// ────────────────────────────────────────────────

route('GET', /^\/llm-profiles$/, async (state) => {
  await sleepGet();
  return { ...state.llmProfiles };
});

route('PATCH', /^\/llm-profiles\/([^/]+)$/, async (state, _m, path, body) => {
  await sleepGet();
  const role = path.match(/\/llm-profiles\/([^/]+)$/)![1];
  const profile = state.llmProfiles.items.find(p => p.role === role);
  if (!profile) throw new ApiError(404, 'profile not found');
  Object.assign(profile, body as Partial<LlmProfile>);
  return { ...profile };
});

route('GET', /^\/llm-models$/, async () => {
  await sleepGet();
  return { models: DEMO_LLM_MODELS };
});

// ────────────────────────────────────────────────
// Helper: dispatch a request through the route table
// ────────────────────────────────────────────────

export async function dispatchDemo(
  state: DemoState,
  method: string,
  path: string,
  body?: unknown
): Promise<unknown> {
  for (const route of ROUTES) {
    if (route.method === method && route.pattern.test(path)) {
      return route.handler(state, method, path, body);
    }
  }
  throw new ApiError(404, `Demo: no route for ${method} ${path}`);
}

/** Default dispatch using module singleton */
export async function defaultDispatch(method: string, path: string, body?: unknown): Promise<unknown> {
  return dispatchDemo(getDemoState(), method, path, body);
}

// ────────────────────────────────────────────────
// Internal helpers
// ────────────────────────────────────────────────

function getCurrentUser(state: DemoState) {
  let userId = state.currentUserId;
  if (!userId) {
    // In-memory state resets on page reload; recover identity from the
    // persisted bearer token (format: demo-<userId>-<timestamp>).
    const m = getToken()?.match(/^demo-(.+)-\d+$/);
    if (m) {
      userId = m[1];
      state.currentUserId = userId;
    }
  }
  if (!userId) throw new ApiError(401, '未登录');
  const user = DEMO_USERS.find(u => u.id === userId);
  if (!user) throw new ApiError(401, '用户不存在');
  return user;
}

function getTrace(state: DemoState, id: string) {
  const tr = state.traces.get(id);
  if (!tr) throw new ApiError(404, 'trace not found');
  return tr;
}

function materializeTraceA(
  state: DemoState,
  traceId: string,
  actor: { display_name: string; role: string },
) {
  const now = new Date();
  const eventDefs = [
    { event: 'REQUEST_RECEIVED', cap: 'data' as const, payload: { role: actor.role, instruction: '张伟退款加急' } },
    { event: 'PLAN_GENERATED', cap: 'data' as const, payload: { steps: 4 } },
    { event: 'POLICY_EVALUATED', cap: 'trusted' as const, payload: { op: 'refund.expedite', decision: 'allow' } },
    { event: 'CONFIRMATION_REQUESTED', cap: 'parsed' as const, payload: { level: 'confirm', writes: 1 } },
    { event: 'USER_CONFIRMED', cap: 'trusted' as const, payload: { approver: actor.display_name } },
    { event: 'OPERATION_EXECUTED', cap: 'write' as const, payload: { op: 'refund.expedite', latency_ms: 158 } },
    { event: 'DATAFLOW_SNAPSHOT', cap: 'data' as const, payload: { nodes: 5, edges: 4 } },
    { event: 'RESPONSE_SENT', cap: 'data' as const, payload: { tokens: 1150 } },
  ];

  const hashes = buildHashChain(eventDefs);
  const auditEvents: AuditEvent[] = eventDefs.map((def, i) => ({
    seq: i + 1,
    event: def.event,
    cap: def.cap,
    payload: def.payload,
    hash: hashes[i].hash,
    prev_hash: hashes[i].prev_hash,
    created_at: new Date(now.getTime() + i * 1000).toISOString(),
  }));

  const flowNodes: FlowNode[] = [
    { node_id: 'n0', label: 'user_input("张伟")', cap: 'trusted', capability_set: ['trusted'], source: 'user', readers: 'emp, admin', via: '可信通道' },
    { node_id: 'n1', label: 'customer_query → customer', cap: 'data', capability_set: ['data'], source: 'query', readers: 'emp, admin', via: 'customer.query' },
    { node_id: 'n2', label: 'order_query → orders', cap: 'data', capability_set: ['data'], source: 'query', readers: 'emp, admin', via: 'order.query' },
    { node_id: 'n3', label: 'Q-LLM → refund_orders', cap: 'parsed', capability_set: ['parsed'], source: 'parse', readers: 'emp, admin', via: 'Q-LLM (无放宽)' },
    { node_id: 'n4', label: 'expedite_refund → result', cap: 'write', capability_set: ['write'], source: 'write', readers: 'emp, admin', via: 'refund.expedite' },
  ];
  const flowEdges: FlowEdge[] = [
    { from: 'n0', to: 'n1', kind: 'query' },
    { from: 'n1', to: 'n2', kind: 'query' },
    { from: 'n2', to: 'n3', kind: 'parse' },
    { from: 'n3', to: 'n4', kind: 'write' },
  ];
  const executions: Execution[] = [
    {
      id: nextId(state, 'exec'),
      op_key: 'refund.expedite',
      executor: 'FunctionExecutor',
      status: 'ok',
      before: { refund_status: 'pending', amount: 299 },
      after: { refund_status: 'expedited', amount: 299 },
      latency_ms: 158,
      error_code: null,
    },
  ];

  state.traces.set(traceId, {
    summary: {
      id: traceId,
      title: '张伟退款加急处理',
      status: 'done',
      acting_role: actor.role,
      created_at: now.toISOString(),
    },
    flowNodes,
    flowEdges,
    auditEvents,
    executions,
  });
}

function materializeTraceC(state: DemoState, traceId: string, _userId: string) {
  const now = new Date();
  const eventDefs = [
    { event: 'REQUEST_RECEIVED', cap: 'data' as const, payload: { role: 'customer', scope: 'self' } },
    { event: 'PLAN_GENERATED', cap: 'data' as const, payload: { steps: 2 } },
    { event: 'OPERATION_EXECUTED', cap: 'data' as const, payload: { op: 'order.query', latency_ms: 45 } },
    { event: 'RESPONSE_SENT', cap: 'data' as const, payload: { tokens: 320 } },
  ];
  const hashes = buildHashChain(eventDefs);
  const auditEvents: AuditEvent[] = eventDefs.map((def, i) => ({
    seq: i + 1,
    event: def.event,
    cap: def.cap,
    payload: def.payload,
    hash: hashes[i].hash,
    prev_hash: hashes[i].prev_hash,
    created_at: new Date(now.getTime() + i * 500).toISOString(),
  }));

  state.traces.set(traceId, {
    summary: { id: traceId, title: '订单查询', status: 'done', acting_role: 'customer', created_at: now.toISOString() },
    flowNodes: [
      { node_id: 'n0', label: 'user_query', cap: 'trusted', capability_set: ['trusted'], source: 'user', readers: 'self', via: '可信通道' },
      { node_id: 'n1', label: 'order.query → orders', cap: 'data', capability_set: ['data'], source: 'query', readers: 'self', via: 'order.query' },
    ],
    flowEdges: [{ from: 'n0', to: 'n1', kind: 'query' }],
    auditEvents,
    executions: [],
  });
}
