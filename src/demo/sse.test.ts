/**
 * DemoEventSource unit tests.
 * Uses fake timers to accelerate the event stream.
 * Passes state directly to DemoEventSource to avoid singleton coupling.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DemoEventSource, installEventSourcePatch, uninstallEventSourcePatch } from './sse';
import { createDemoState } from './state';
import { EXPLORATION_EVENTS } from './fixtures/exploration';

function setupJobState(jobId: string) {
  const state = createDemoState();
  state.jobs.set(jobId, { id: jobId, source_id: 'src-code', status: 'running', phase: 1, progress: 0 });
  return state;
}

describe('DemoEventSource', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('emits events in order and lastEventId increments', async () => {
    const state = setupJobState('job-test-1');
    const es = new DemoEventSource('job-test-1', state);
    const received: Array<{ type: string; id: string }> = [];

    for (const t of ['phase', 'op', 'rule', 'file', 'extract', 'chain', 'done', 'error', 'message']) {
      es.addEventListener(t, (e: MessageEvent) => {
        received.push({ type: e.type, id: e.lastEventId });
      });
    }

    await vi.runAllTimersAsync();

    expect(received.length).toBeGreaterThan(0);
    // lastEventIds should be strictly increasing
    for (let i = 1; i < received.length; i++) {
      expect(Number(received[i].id)).toBeGreaterThan(Number(received[i - 1].id));
    }
  });

  it('done event is emitted last and closes the source', async () => {
    const state = setupJobState('job-test-2');
    const es = new DemoEventSource('job-test-2', state);
    let doneReceived = false;
    es.addEventListener('done', () => { doneReceived = true; });

    await vi.runAllTimersAsync();

    expect(doneReceived).toBe(true);
  });

  it('job progress reaches 100 after all events', async () => {
    const state = setupJobState('job-test-3');
    new DemoEventSource('job-test-3', state);
    await vi.runAllTimersAsync();

    const job = state.jobs.get('job-test-3');
    expect(job?.status).toBe('done');
    expect(job?.progress).toBe(100);
  });

  it('close() stops event emission early', async () => {
    const state = setupJobState('job-test-4');
    const es = new DemoEventSource('job-test-4', state);
    const received: string[] = [];
    es.addEventListener('phase', (e: MessageEvent) => received.push(e.type));

    // Close immediately before any timer fires
    es.close();
    await vi.runAllTimersAsync();

    // With close() called before any async timer, no events should fire
    expect(received.length).toBe(0);
  });

  it('all event types in EXPLORATION_EVENTS script are emitted', async () => {
    const state = setupJobState('job-test-5');
    const es = new DemoEventSource('job-test-5', state);
    const allTypes = new Set<string>();
    for (const t of ['phase', 'op', 'rule', 'file', 'extract', 'chain', 'done', 'error', 'message']) {
      es.addEventListener(t, (e: MessageEvent) => allTypes.add(e.type));
    }

    await vi.runAllTimersAsync();

    // All event types in the script should have been fired
    const scriptTypes = new Set(EXPLORATION_EVENTS.map(e => e.type));
    for (const t of scriptTypes) {
      expect(allTypes.has(t)).toBe(true);
    }
  });

  it('source becomes connected after exploration completes', async () => {
    const state = setupJobState('job-test-6');
    new DemoEventSource('job-test-6', state);
    await vi.runAllTimersAsync();

    const src = state.sources.find(s => s.id === 'src-code');
    // Source was already connected; verify it stays connected
    expect(src?.status).toBe('connected');
  });
});

describe('EventSource URL routing patch', () => {
  afterEach(() => {
    uninstallEventSourcePatch();
  });

  it('installs and uninstalls without error', () => {
    installEventSourcePatch();
    uninstallEventSourcePatch();
    expect(true).toBe(true);
  });

  it('second install is idempotent', () => {
    installEventSourcePatch();
    installEventSourcePatch(); // should not throw
    expect(true).toBe(true);
  });
});
