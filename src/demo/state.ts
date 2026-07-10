/**
 * Demo state store — all mutable demo state lives here.
 * createDemoState() returns a fresh isolated instance (for tests).
 * The module-level singleton is used by install.ts/router.ts at runtime.
 */

import type {
  ApprovalRequest, ApprovalVote, AuditEvent, ChatMessage, ChatSession,
  DataSource, Execution, ExplorationJob, FlowEdge, FlowNode,
  LlmProfile, Operation, TraceSummary,
} from '../api/types';
import { DEMO_SOURCES } from './fixtures/sources';
import { DEMO_OPERATIONS } from './fixtures/operations';
import {
  SEED_AUDIT_EVENTS, SEED_EXECUTIONS,
  SEED_FLOW_EDGES, SEED_FLOW_NODES,
  SEED_TRACE_ID, SEED_TRACE_SUMMARY,
} from './fixtures/traces';
import { DEMO_LLM_PROFILES } from './fixtures/llm';
import { fakeId } from './hash';

export interface TraceData {
  summary: TraceSummary;
  flowNodes: FlowNode[];
  flowEdges: FlowEdge[];
  auditEvents: AuditEvent[];
  executions: Execution[];
}

export interface DemoSession {
  id: string;
  userId: string;
  title: string;
  messages: ChatMessage[];
}

export interface DemoState {
  /** Current logged-in user id (null = not logged in) */
  currentUserId: string | null;

  /** Token store (fake tokens) */
  tokens: Map<string, string>; // token → userId

  /** Chat sessions per user */
  sessions: Map<string, DemoSession>; // sessionId → session

  /** Traces */
  traces: Map<string, TraceData>; // traceId → TraceData

  /** Operations (can grow when exploration completes) */
  operations: Operation[];

  /** Data sources */
  sources: DataSource[];

  /** Approval requests */
  approvals: ApprovalRequest[];

  /** Exploration jobs */
  jobs: Map<string, ExplorationJob>;

  /** LLM profiles (patchable) */
  llmProfiles: { base_url: string; items: LlmProfile[] };

  /** Counter for generating unique IDs within a session */
  counter: number;
}

export function createDemoState(): DemoState {
  // Deep clone sources so tests don't share mutable state
  const sources: DataSource[] = DEMO_SOURCES.map(s => ({ ...s }));
  const operations: Operation[] = DEMO_OPERATIONS.map(o => ({ ...o }));

  const traces = new Map<string, TraceData>();
  traces.set(SEED_TRACE_ID, {
    summary: { ...SEED_TRACE_SUMMARY },
    flowNodes: SEED_FLOW_NODES.map(n => ({ ...n })),
    flowEdges: SEED_FLOW_EDGES.map(e => ({ ...e })),
    auditEvents: SEED_AUDIT_EVENTS.map(e => ({ ...e })),
    executions: SEED_EXECUTIONS.map(e => ({ ...e })),
  });

  return {
    currentUserId: null,
    tokens: new Map(),
    sessions: new Map(),
    traces,
    operations,
    sources,
    approvals: [],
    jobs: new Map(),
    llmProfiles: {
      base_url: DEMO_LLM_PROFILES.base_url,
      items: DEMO_LLM_PROFILES.items.map(p => ({ ...p })),
    },
    counter: 1,
  };
}

/** Generate a short unique ID using state counter */
export function nextId(state: DemoState, prefix: string): string {
  return `${prefix}-${state.counter++}`;
}

/** Generate a fake ID deterministically from a string seed */
export function genId(seed: string): string {
  return fakeId(seed);
}

// Module-level singleton
let _singleton: DemoState | null = null;

export function getDemoState(): DemoState {
  if (!_singleton) _singleton = createDemoState();
  return _singleton;
}

export function resetDemoState(): void {
  _singleton = null;
}
