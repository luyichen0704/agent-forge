/** Demo trace fixtures — historical "张伟退款加急" trace from seed.py */
import type { AuditEvent, Execution, FlowEdge, FlowNode, TraceSummary } from '../../api/types';

export const SEED_TRACE_ID = 'tr-seed-001';

export const SEED_TRACE_SUMMARY: TraceSummary = {
  id: SEED_TRACE_ID,
  title: '张伟退款加急',
  status: 'closed',
  acting_role: 'employee',
  created_at: '2024-11-01T10:30:00+00:00',
};

export const SEED_FLOW_NODES: FlowNode[] = [
  { node_id: 'n0', label: 'user_input("张伟")', cap: 'trusted', capability_set: ['trusted'], source: 'user', readers: 'emp, admin', via: '可信通道' },
  { node_id: 'n1', label: 'customer_query → customer', cap: 'data', capability_set: ['data'], source: 'query', readers: 'emp, admin', via: 'customer.query' },
  { node_id: 'n2', label: 'order_query → orders', cap: 'data', capability_set: ['data'], source: 'query', readers: 'emp, admin', via: 'order.query' },
  { node_id: 'n3', label: 'Q-LLM → refund_orders', cap: 'parsed', capability_set: ['parsed'], source: 'parse', readers: 'emp, admin', via: 'Q-LLM (无放宽)' },
  { node_id: 'n4', label: 'expedite_refund → result', cap: 'write', capability_set: ['write'], source: 'write', readers: 'emp, admin', via: 'refund.expedite' },
];

export const SEED_FLOW_EDGES: FlowEdge[] = [
  { from: 'n0', to: 'n1', kind: 'query' },
  { from: 'n1', to: 'n2', kind: 'query' },
  { from: 'n2', to: 'n3', kind: 'parse' },
  { from: 'n3', to: 'n4', kind: 'write' },
];

export const SEED_EXECUTIONS: Execution[] = [
  {
    id: 'exec-seed-001',
    op_key: 'refund.expedite',
    executor: 'FunctionExecutor',
    status: 'ok',
    before: { refund_status: 'pending', amount: 299 },
    after: { refund_status: 'expedited', amount: 299 },
    latency_ms: 142,
    error_code: null,
  },
];

// Seed audit events — deterministic hashes (generated once, hardcoded)
export const SEED_AUDIT_EVENTS: AuditEvent[] = [
  {
    seq: 1, event: 'REQUEST_RECEIVED', cap: 'data',
    payload: { role: 'employee', instruction: '张伟退款加急' },
    hash: 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
    prev_hash: '0000000000000000000000000000000000000000000000000000000000000000',
    created_at: '2024-11-01T10:30:00+00:00',
  },
  {
    seq: 2, event: 'PLAN_GENERATED', cap: 'data',
    payload: { steps: 5 },
    hash: 'b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3',
    prev_hash: 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
    created_at: '2024-11-01T10:30:02+00:00',
  },
  {
    seq: 3, event: 'POLICY_EVALUATED', cap: 'trusted',
    payload: { op: 'refund.expedite', decision: 'allow' },
    hash: 'c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4',
    prev_hash: 'b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3',
    created_at: '2024-11-01T10:30:03+00:00',
  },
  {
    seq: 4, event: 'CONFIRMATION_REQUESTED', cap: 'parsed',
    payload: { level: 'confirm', writes: 1 },
    hash: 'd4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5',
    prev_hash: 'c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4',
    created_at: '2024-11-01T10:30:04+00:00',
  },
  {
    seq: 5, event: 'USER_CONFIRMED', cap: 'trusted',
    payload: { approver: '员工小卫' },
    hash: 'e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6',
    prev_hash: 'd4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5',
    created_at: '2024-11-01T10:30:25+00:00',
  },
  {
    seq: 6, event: 'OPERATION_EXECUTED', cap: 'write',
    payload: { op: 'refund.expedite', latency_ms: 142 },
    hash: 'f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1',
    prev_hash: 'e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6',
    created_at: '2024-11-01T10:30:26+00:00',
  },
  {
    seq: 7, event: 'DATAFLOW_SNAPSHOT', cap: 'data',
    payload: { nodes: 5, edges: 4 },
    hash: 'a7b8c9d0e1f2a7b8c9d0e1f2a7b8c9d0e1f2a7b8c9d0e1f2a7b8c9d0e1f2a7b8',
    prev_hash: 'f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1',
    created_at: '2024-11-01T10:30:27+00:00',
  },
  {
    seq: 8, event: 'RESPONSE_SENT', cap: 'data',
    payload: { tokens: 1200 },
    hash: 'b8c9d0e1f2a3b8c9d0e1f2a3b8c9d0e1f2a3b8c9d0e1f2a3b8c9d0e1f2a3b8c9',
    prev_hash: 'a7b8c9d0e1f2a7b8c9d0e1f2a7b8c9d0e1f2a7b8c9d0e1f2a7b8c9d0e1f2a7b8',
    created_at: '2024-11-01T10:30:28+00:00',
  },
];
