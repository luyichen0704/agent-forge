/**
 * DemoEventSource — implements the interface used by useExplorationStream.
 * Only intercepts URLs matching /exploration-jobs/.+/events.
 * All other URLs are delegated to the native EventSource.
 */

import { EXPLORATION_EVENTS } from './fixtures/exploration';
import { getDemoState } from './state';
import type { DemoState } from './state';

const EXPLORE_PATTERN = /\/exploration-jobs\/([^/?]+)\/events/;

type EventListenerFn = (event: MessageEvent) => void;

export class DemoEventSource {
  private _listeners: Map<string, EventListenerFn[]> = new Map();
  private _closed = false;
  private _seqCounter = 0;
  public lastEventId = '';
  public onerror: ((e: Event) => void) | null = null;

  constructor(private readonly jobId: string, private readonly _stateOverride?: DemoState) {
    // Start the event stream asynchronously
    this._start();
  }

  addEventListener(type: string, listener: EventListenerFn): void {
    if (!this._listeners.has(type)) this._listeners.set(type, []);
    this._listeners.get(type)!.push(listener);
  }

  close(): void {
    this._closed = true;
  }

  private _emit(type: string, payload: Record<string, unknown>): void {
    if (this._closed) return;
    this._seqCounter++;
    this.lastEventId = String(this._seqCounter);
    const event = new MessageEvent(type, {
      data: JSON.stringify(payload),
      lastEventId: this.lastEventId,
    });
    const listeners = this._listeners.get(type) ?? [];
    for (const fn of listeners) fn(event);
  }

  private async _start(): Promise<void> {
    const state = this._stateOverride ?? getDemoState();
    const job = state.jobs.get(this.jobId);

    let eventIdx = 0;
    let currentPhase = 1;
    const totalEvents = EXPLORATION_EVENTS.length;

    for (const ev of EXPLORATION_EVENTS) {
      if (this._closed) return;
      await sleep(ev.delayMs);
      if (this._closed) return;

      // Update job progress
      if (job) {
        eventIdx++;
        job.progress = Math.round((eventIdx / totalEvents) * 100);
        if (ev.type === 'phase') {
          currentPhase = (ev.payload.phase as number) ?? currentPhase;
          job.phase = currentPhase;
        }
      }

      this._emit(ev.type, ev.payload);

      if (ev.type === 'done') {
        // Finalize job and state
        if (job) {
          job.status = 'done';
          job.progress = 100;
          // Update source to connected
          const src = state.sources.find(s => s.id === job.source_id);
          if (src) src.status = 'connected';
        }
        // Add new operations discovered during exploration
        addDiscoveredOperations(state);
        // Send close event
        this._emit('close' as string, {});
        this.close();
        return;
      }
    }

    if (job) {
      job.status = 'done';
      job.progress = 100;
    }
    this._emit('done', { operations: 5, total_rules: 4 });
    this.close();
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/** After exploration, add 3 pending drafts + 2 active operations */
function addDiscoveredOperations(state: import('./state').DemoState): void {
  // Check if already added
  if (state.operations.find(o => o.op_key === 'order.search')) return;

  const newOps: import('../api/types').Operation[] = [
    {
      id: `op-order-search-${Date.now()}`, op_key: 'order.search', version: 1,
      kind: 'query', confirm_level: 'auto', risk_level: 'low', status: 'pending',
      executor_binding: 'FunctionExecutor', policy_ref: null,
      roles: ['employee', 'admin'], perm: 'allow', scopes: {},
    },
    {
      id: `op-customer-update-tier-${Date.now()}`, op_key: 'customer.update_tier', version: 1,
      kind: 'mutation', confirm_level: 'confirm', risk_level: 'medium', status: 'pending',
      executor_binding: 'FunctionExecutor', policy_ref: null,
      roles: ['admin'], perm: 'allow', scopes: {},
    },
    {
      id: `op-report-generate-${Date.now()}`, op_key: 'report.generate', version: 1,
      kind: 'query', confirm_level: 'auto', risk_level: 'low', status: 'pending',
      executor_binding: 'FunctionExecutor', policy_ref: null,
      roles: ['employee', 'admin'], perm: 'allow', scopes: {},
    },
    // 2 active query operations
    {
      id: `op-customer-list-${Date.now()}`, op_key: 'customer.list', version: 1,
      kind: 'query', confirm_level: 'auto', risk_level: 'low', status: 'active',
      executor_binding: 'FunctionExecutor', policy_ref: 'customer_list_policy',
      roles: ['employee', 'admin'], perm: 'allow', scopes: {},
    },
    {
      id: `op-order-stats-${Date.now()}`, op_key: 'order.stats', version: 1,
      kind: 'query', confirm_level: 'auto', risk_level: 'low', status: 'active',
      executor_binding: 'FunctionExecutor', policy_ref: 'order_stats_policy',
      roles: ['employee', 'admin'], perm: 'allow', scopes: {},
    },
  ];

  state.operations.push(...newOps);
}

// ────────────────────────────────────────────────
// EventSource patch — replaces window.EventSource for demo URLs
// ────────────────────────────────────────────────

let _originalEventSource: typeof EventSource | null = null;

export function installEventSourcePatch(): void {
  if (_originalEventSource) return; // already installed
  _originalEventSource = window.EventSource;

  // Patch window.EventSource
  (window as unknown as Record<string, unknown>).EventSource = class PatchedEventSource {
    private _inner: DemoEventSource | EventSource;

    constructor(url: string) {
      const match = url.match(EXPLORE_PATTERN);
      if (match) {
        this._inner = new DemoEventSource(match[1]);
      } else {
        this._inner = new _originalEventSource!(url);
      }
    }

    get lastEventId(): string {
      return (this._inner as DemoEventSource).lastEventId ?? '';
    }

    set onerror(fn: ((e: Event) => void) | null) {
      (this._inner as DemoEventSource).onerror = fn;
    }

    addEventListener(type: string, listener: EventListenerFn): void {
      this._inner.addEventListener(type, listener as EventListener);
    }

    close(): void {
      this._inner.close();
    }
  };
}

export function uninstallEventSourcePatch(): void {
  if (_originalEventSource) {
    (window as unknown as Record<string, unknown>).EventSource = _originalEventSource;
    _originalEventSource = null;
  }
}
