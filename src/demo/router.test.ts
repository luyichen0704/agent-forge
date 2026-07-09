/**
 * Demo router unit tests.
 * Uses createDemoState() for full isolation per test.
 * Uses fake timers to skip real delays.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { dispatchDemo } from './router';
import { createDemoState } from './state';
import type { DemoState } from './state';
import type { ChatMessage, Me, Plan } from '../api/types';

// Stub all pacing sleeps to resolve instantly
vi.mock('./pacing', () => ({
  sleep: () => Promise.resolve(),
  sleepGet: () => Promise.resolve(),
  sleepSend: () => Promise.resolve(),
  sleepConfirm: () => Promise.resolve(),
  sleepVote: () => Promise.resolve(),
}));

let state: DemoState;

beforeEach(() => {
  state = createDemoState();
  localStorage.clear();
});

// ────────────────────────────────────────────────
// Auth
// ────────────────────────────────────────────────

describe('auth', () => {
  it('password login succeeds with correct credentials', async () => {
    const res = await dispatchDemo(state, 'POST', '/auth/token', { email: 'wei@company.com', password: 'demo1234' }) as { token: string };
    expect(res.token).toBeTruthy();
    expect(state.currentUserId).toBe('u-wei');
  });

  it('password login fails with wrong password', async () => {
    await expect(
      dispatchDemo(state, 'POST', '/auth/token', { email: 'wei@company.com', password: 'wrong' })
    ).rejects.toThrow(ApiError);
  });

  it('returns correct allowed_screens for customer role', async () => {
    await dispatchDemo(state, 'POST', '/auth/token', { email: 'zhang@demo.com', password: 'demo1234' });
    const me = await dispatchDemo(state, 'GET', '/me', undefined) as Me;
    expect(me.acting_role).toBe('customer');
    expect(me.allowed_screens).toEqual(['chat', 'flow']);
  });

  it('returns correct allowed_screens for employee role', async () => {
    await dispatchDemo(state, 'POST', '/auth/token', { email: 'wei@company.com', password: 'demo1234' });
    const me = await dispatchDemo(state, 'GET', '/me', undefined) as Me;
    expect(me.acting_role).toBe('employee');
    expect(me.allowed_screens).toEqual(['chat', 'flow', 'live', 'ops']);
  });

  it('returns all screens for admin role', async () => {
    await dispatchDemo(state, 'POST', '/auth/token', { email: 'admin@company.com', password: 'demo1234' });
    const me = await dispatchDemo(state, 'GET', '/me', undefined) as Me;
    expect(me.acting_role).toBe('admin');
    expect(me.allowed_screens).toContain('explore');
    expect(me.allowed_screens).toContain('audit');
    expect(me.allowed_screens).toContain('plugins');
  });

  it('/me throws 401 if not logged in', async () => {
    await expect(dispatchDemo(state, 'GET', '/me', undefined)).rejects.toThrow(ApiError);
  });

  it('/me recovers identity from persisted token after state reset (page reload)', async () => {
    const res = await dispatchDemo(state, 'POST', '/auth/login', { role: 'employee' }) as { token: string };
    localStorage.setItem('agentforge.token', res.token);
    const fresh = createDemoState(); // simulates reload: in-memory state gone, token persisted
    const me = await dispatchDemo(fresh, 'GET', '/me', undefined) as Me;
    expect(me.acting_role).toBe('employee');
    expect(fresh.currentUserId).toBe('u-wei');
  });
});

// ────────────────────────────────────────────────
// Chat — Scenario A
// ────────────────────────────────────────────────

describe('chat scenario A — refund expedite', () => {
  async function setupSession() {
    await dispatchDemo(state, 'POST', '/auth/token', { email: 'wei@company.com', password: 'demo1234' });
    const { id: sessId } = await dispatchDemo(state, 'POST', '/chat/sessions', undefined) as { id: string };
    return sessId;
  }

  it('send standard instruction returns 4-step plan in awaiting_confirm', async () => {
    const sessId = await setupSession();
    const res = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: '查一下张伟的退款单，把还在 pending 的加急处理',
    }) as { reply: string; plan: Plan };

    expect(res.plan.status).toBe('awaiting_confirm');
    expect(res.plan.steps).toHaveLength(4);
    expect(res.plan.required_confirm_level).toBe('confirm');
    expect(res.plan.writes).toBe(1);
    // Reply follows the template
    expect(res.reply).toContain('需要确认');
  });

  it('confirm plan returns done plan with trace materialized', async () => {
    const sessId = await setupSession();
    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: '退款加急',
    }) as { plan: Plan };

    const confirmed = await dispatchDemo(state, 'POST', `/plans/${plan.id}/confirm`, undefined) as Plan;
    expect(confirmed.status).toBe('done');
    expect(confirmed.blocked).toBe(false);

    // Refetched messages must see the updated plan status (same object ref),
    // otherwise the chat plan card keeps showing the 确认执行 button.
    const msgs = await dispatchDemo(state, 'GET', `/chat/sessions/${sessId}/messages`, undefined) as { items: ChatMessage[] };
    const planMsg = msgs.items.find(m => m.plan?.id === plan.id);
    expect(planMsg?.plan?.status).toBe('done');

    // Trace should now exist
    const traces = await dispatchDemo(state, 'GET', '/traces', undefined) as { items: Array<{ id: string; title: string }> };
    expect(traces.items[0].id).toBe(plan.trace_id);
  });

  it('new trace has 5 flow nodes', async () => {
    const sessId = await setupSession();
    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: '退款加急',
    }) as { plan: Plan };
    await dispatchDemo(state, 'POST', `/plans/${plan.id}/confirm`, undefined);

    const flow = await dispatchDemo(state, 'GET', `/traces/${plan.trace_id}/flow`, undefined) as { nodes: unknown[] };
    expect(flow.nodes).toHaveLength(5);
  });

  it('new trace audit has 8 events with valid hash chain', async () => {
    const sessId = await setupSession();
    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: '退款加急',
    }) as { plan: Plan };
    await dispatchDemo(state, 'POST', `/plans/${plan.id}/confirm`, undefined);

    const audit = await dispatchDemo(state, 'GET', `/traces/${plan.trace_id}/audit`, undefined) as {
      verification: { valid: boolean };
      events: unknown[];
    };
    expect(audit.events).toHaveLength(8);
    expect(audit.verification.valid).toBe(true);
  });

  it('execution before/after reflects refund_status change', async () => {
    const sessId = await setupSession();
    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: '退款加急',
    }) as { plan: Plan };
    await dispatchDemo(state, 'POST', `/plans/${plan.id}/confirm`, undefined);

    const execs = await dispatchDemo(state, 'GET', `/traces/${plan.trace_id}/executions`, undefined) as { items: Array<{ before: Record<string, unknown>; after: Record<string, unknown> }> };
    expect(execs.items[0].before.refund_status).toBe('pending');
    expect(execs.items[0].after.refund_status).toBe('expedited');
  });

  it('cancel plan sets status to cancelled', async () => {
    const sessId = await setupSession();
    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: '退款加急',
    }) as { plan: Plan };

    const cancelled = await dispatchDemo(state, 'POST', `/plans/${plan.id}/cancel`, undefined) as { status: string };
    expect(cancelled.status).toBe('cancelled');
  });
});

// ────────────────────────────────────────────────
// Chat — Scenario B dual approval
// ────────────────────────────────────────────────

describe('chat scenario B — dual approval salary', () => {
  async function loginAsAdmin(email = 'admin@company.com') {
    await dispatchDemo(state, 'POST', '/auth/token', { email, password: 'demo1234' });
    const { id } = await dispatchDemo(state, 'POST', '/chat/sessions', undefined) as { id: string };
    return id;
  }

  it('salary instruction returns blocked=true plan', async () => {
    const sessId = await loginAsAdmin();
    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: '帮我设置薪资',
    }) as { plan: Plan };

    expect(plan.required_confirm_level).toBe('dual');
    expect(plan.blocked).toBe(true);
    expect(state.approvals).toHaveLength(1);
    expect(state.approvals[0].status).toBe('pending');
    expect(state.approvals[0].required_votes).toBe(2);
  });

  it('confirm with only 1 vote still returns blocked=true', async () => {
    const sessId = await loginAsAdmin();
    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: '薪资',
    }) as { plan: Plan };

    // First admin votes
    const appr = state.approvals[0];
    await dispatchDemo(state, 'POST', `/approval-requests/${appr.id}/votes`, { decision: 'approve' });

    const confirmed = await dispatchDemo(state, 'POST', `/plans/${plan.id}/confirm`, undefined) as Plan;
    expect(confirmed.blocked).toBe(true);
  });

  it('same approver cannot vote twice (409)', async () => {
    const sessId = await loginAsAdmin();
    await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, { content: '薪资' });
    const appr = state.approvals[0];

    await dispatchDemo(state, 'POST', `/approval-requests/${appr.id}/votes`, { decision: 'approve' });
    await expect(
      dispatchDemo(state, 'POST', `/approval-requests/${appr.id}/votes`, { decision: 'approve' })
    ).rejects.toMatchObject({ status: 409, message: '同一审批人不能重复投票' });
  });

  it('second admin vote approves the request', async () => {
    const sessId = await loginAsAdmin();
    await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, { content: '薪资' });
    const appr = state.approvals[0];

    // First vote (admin)
    await dispatchDemo(state, 'POST', `/approval-requests/${appr.id}/votes`, { decision: 'approve' });

    // Second vote (admin2)
    state.currentUserId = 'u-admin2';
    await dispatchDemo(state, 'POST', `/approval-requests/${appr.id}/votes`, { decision: 'approve' });

    expect(appr.status).toBe('approved');
    expect(appr.approve_votes).toBe(2);
  });
});

// ────────────────────────────────────────────────
// Chat — Scenario C (fallback)
// ────────────────────────────────────────────────

describe('chat scenario C — auto query', () => {
  it('query instruction returns auto done plan', async () => {
    await dispatchDemo(state, 'POST', '/auth/token', { email: 'zhang@demo.com', password: 'demo1234' });
    const { id: sessId } = await dispatchDemo(state, 'POST', '/chat/sessions', undefined) as { id: string };

    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: '查询我的订单',
    }) as { plan: Plan };

    expect(plan.required_confirm_level).toBe('auto');
    expect(plan.status).toBe('done');
    expect(plan.writes).toBe(0);
  });

  it('unrecognized text (fallback) returns auto done plan', async () => {
    await dispatchDemo(state, 'POST', '/auth/token', { email: 'wei@company.com', password: 'demo1234' });
    const { id: sessId } = await dispatchDemo(state, 'POST', '/chat/sessions', undefined) as { id: string };

    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, {
      content: 'asdfghjkl随便打的',
    }) as { plan: Plan };

    expect(plan.required_confirm_level).toBe('auto');
    expect(plan.status).toBe('done');
  });
});

// ────────────────────────────────────────────────
// Operations
// ────────────────────────────────────────────────

describe('operations', () => {
  it('returns all 6 operations', async () => {
    await dispatchDemo(state, 'POST', '/auth/token', { email: 'admin@company.com', password: 'demo1234' });
    const res = await dispatchDemo(state, 'GET', '/operations', undefined) as { items: unknown[]; total: number };
    expect(res.total).toBe(6);
  });

  it('publish changes status to active', async () => {
    await dispatchDemo(state, 'POST', '/auth/token', { email: 'admin@company.com', password: 'demo1234' });
    const op = state.operations.find(o => o.status === 'pending')!;
    await dispatchDemo(state, 'POST', `/operations/${op.id}/publish`, undefined);
    expect(state.operations.find(o => o.id === op.id)?.status).toBe('active');
  });
});

// ────────────────────────────────────────────────
// Traces (seed data)
// ────────────────────────────────────────────────

describe('seed trace', () => {
  it('traces list includes seed trace', async () => {
    await dispatchDemo(state, 'POST', '/auth/token', { email: 'admin@company.com', password: 'demo1234' });
    const res = await dispatchDemo(state, 'GET', '/traces', undefined) as { items: Array<{ id: string }> };
    expect(res.items.some(t => t.id === 'tr-seed-001')).toBe(true);
  });

  it('seed trace flow has 5 nodes', async () => {
    const flow = await dispatchDemo(state, 'GET', '/traces/tr-seed-001/flow', undefined) as { nodes: unknown[] };
    expect(flow.nodes).toHaveLength(5);
  });

  it('seed trace audit has 8 events', async () => {
    const audit = await dispatchDemo(state, 'GET', '/traces/tr-seed-001/audit', undefined) as { events: unknown[]; verification: { valid: boolean } };
    expect(audit.events).toHaveLength(8);
    expect(audit.verification.valid).toBe(true);
  });

  it('rollback changes execution status', async () => {
    const execs = await dispatchDemo(state, 'GET', '/traces/tr-seed-001/executions', undefined) as { items: Array<{ id: string }> };
    const execId = execs.items[0].id;
    await dispatchDemo(state, 'POST', `/executions/${execId}/rollback`, undefined);
    const updated = await dispatchDemo(state, 'GET', '/traces/tr-seed-001/executions', undefined) as { items: Array<{ status: string }> };
    expect(updated.items[0].status).toBe('rolled_back');
  });
});

// ────────────────────────────────────────────────
// LLM profiles
// ────────────────────────────────────────────────

describe('llm profiles', () => {
  it('GET /llm-profiles returns 2 items', async () => {
    const res = await dispatchDemo(state, 'GET', '/llm-profiles', undefined) as { items: unknown[] };
    expect(res.items).toHaveLength(2);
  });

  it('PATCH /llm-profiles/:role updates model', async () => {
    await dispatchDemo(state, 'PATCH', '/llm-profiles/pllm', { model: 'gpt-4o' });
    const res = await dispatchDemo(state, 'GET', '/llm-profiles', undefined) as { items: Array<{ role: string; model: string }> };
    expect(res.items.find(p => p.role === 'pllm')?.model).toBe('gpt-4o');
  });

  it('GET /llm-models returns model list', async () => {
    const res = await dispatchDemo(state, 'GET', '/llm-models', undefined) as { models: string[] };
    expect(res.models.length).toBeGreaterThan(0);
  });
});

// ────────────────────────────────────────────────
// Hash chain quality (regression: first block was always 00000000)
// ────────────────────────────────────────────────

describe('audit hash chain', () => {
  it('produces non-zero, distinct, linked hashes', async () => {
    await dispatchDemo(state, 'POST', '/auth/login', { role: 'admin' });
    const { id: sessId } = await dispatchDemo(state, 'POST', '/chat/sessions', undefined) as { id: string };
    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, { content: '退款加急' }) as { plan: Plan };
    await dispatchDemo(state, 'POST', `/plans/${plan.id}/confirm`, undefined);
    const traces = await dispatchDemo(state, 'GET', '/traces', undefined) as { items: Array<{ id: string }> };
    const audit = await dispatchDemo(state, 'GET', `/traces/${traces.items[0].id}/audit`, undefined) as {
      events: Array<{ hash: string; prev_hash: string }>;
    };
    expect(audit.events.length).toBeGreaterThan(0);
    for (let i = 0; i < audit.events.length; i++) {
      const ev = audit.events[i];
      expect(ev.hash.slice(0, 8)).not.toBe('00000000');
      expect(ev.hash).toMatch(/^[0-9a-f]{64}$/);
      if (i > 0) expect(ev.prev_hash).toBe(audit.events[i - 1].hash);
    }
    const unique = new Set(audit.events.map(e => e.hash));
    expect(unique.size).toBe(audit.events.length);
  });

  it('hash blocks do not share a trailing-zero pattern (float precision regression)', async () => {
    await dispatchDemo(state, 'POST', '/auth/login', { role: 'admin' });
    const { id: sessId } = await dispatchDemo(state, 'POST', '/chat/sessions', undefined) as { id: string };
    const { plan } = await dispatchDemo(state, 'POST', `/chat/sessions/${sessId}/messages`, { content: '退款加急' }) as { plan: Plan };
    await dispatchDemo(state, 'POST', `/plans/${plan.id}/confirm`, undefined);
    const traces = await dispatchDemo(state, 'GET', '/traces', undefined) as { items: Array<{ id: string }> };
    const audit = await dispatchDemo(state, 'GET', `/traces/${traces.items[0].id}/audit`, undefined) as {
      events: Array<{ hash: string }>;
    };
    const allEndZero = audit.events.every(e => e.hash.slice(6, 8) === '00');
    expect(allEndZero).toBe(false);
  });
});
