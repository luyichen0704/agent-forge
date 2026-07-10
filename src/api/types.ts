/* API DTOs — mirror the FastAPI backend responses (server is source of truth). */

export type Role = 'customer' | 'employee' | 'admin';
export type ScreenKey = 'explore' | 'live' | 'chat' | 'flow' | 'ops' | 'audit' | 'plugins';
export type CapKind = 'trusted' | 'data' | 'parsed' | 'write';

export interface Me {
  user: { id: string; email: string; display_name: string };
  tenant: { id: string; name: string; slug: string };
  acting_role: Role;
  roles: Role[];
  allowed_screens: ScreenKey[];
}

export interface Operation {
  id: string;
  op_key: string;
  version: number;
  kind: 'query' | 'mutation';
  confirm_level: 'auto' | 'confirm' | 'dual';
  risk_level: string;
  status: 'pending' | 'active' | 'disabled';
  executor_binding: string | null;
  policy_ref: string | null;
  roles: Role[];
  perm: string;
  scopes: Record<string, string>;
  // Business-language fields the server now returns (see server/app/api/registry.py::_serialize_with)
  source_id?: string | null;
  source_name?: string | null;
  desc?: string;
  call?: string | null;
}
export interface OperationList { items: Operation[]; pending_count: number; total: number }

export interface DataSource {
  id: string; type: string; name: string; connector_kind: string;
  conn: string; status: string; progress: number | null;
}

export interface PluginImpl { name: string; status: string; version: string; health: string }
export interface Plugin { id: string; iface: string; sub: string; icon: string; code: string; impls: PluginImpl[] }

export interface TraceSummary { id: string; title: string; status: string; acting_role: string; created_at: string }

export interface FlowNode {
  node_id: string; label: string; cap: CapKind; capability_set: string[];
  source: string; readers: string; via: string;
}
export interface FlowEdge { from: string; to: string; kind: string }
export interface TraceFlow { trace_id: string; nodes: FlowNode[]; edges: FlowEdge[] }

export interface AuditEvent {
  seq: number; event: string; cap: CapKind; payload: Record<string, unknown>;
  hash: string; prev_hash: string; created_at: string;
}
export interface TraceAudit {
  trace_id: string;
  verification: { valid: boolean; count: number; head?: string; broken_at_seq?: number };
  events: AuditEvent[];
}

export interface Execution {
  id: string; op_key: string; executor: string; status: string;
  before: Record<string, unknown>; after: Record<string, unknown>;
  latency_ms: number; error_code: string | null;
}

export interface PlanStep {
  step_no: number; kind: 'query' | 'parse' | 'write'; op_key: string | null; label: string;
  capability_in: string[]; capability_out: CapKind; approval_request_id: string | null; status: string;
}
export interface Plan {
  id: string; trace_id: string; intent: string; writes: number;
  required_confirm_level: 'auto' | 'confirm' | 'dual'; status: string;
  reasoning_summary: string; policy_hints: string[]; steps: PlanStep[]; blocked?: boolean;
}

export interface ChatSession { id: string; title: string; source_id?: string | null }
export interface ChatMessage {
  id: string; role: 'user' | 'assistant' | 'system'; content: string; created_at: string; plan: Plan | null;
}

export interface ApprovalVote { approver_id: string; decision: string; comment: string; created_at: string }
export interface ApprovalRequest {
  id: string; trace_id: string | null; target_type: string; target_id: string;
  confirm_level: string; status: string; required_votes: number; approve_votes: number; votes: ApprovalVote[];
}

export interface ExplorationJob { id: string; source_id: string; status: string; phase: number; progress: number }

export interface LlmProfile {
  role: 'pllm' | 'qllm';
  model: string;
  temperature: number;
  max_tokens: number;
  timeout_s: number;
}
export interface LlmProfiles { base_url: string; items: LlmProfile[] }

export interface PolicyRuleCondition {
  field: string;
  op: string;
  value: unknown;
}

export interface PolicyRule {
  id: string;
  rule_id: string;
  description: string | null;
  effect: 'allow' | 'deny';
  confirm_escalation: 'auto' | 'confirm' | 'dual' | null;
  op_keys: string[];
  capability_tags: string[];
  risk_levels: string[];
  roles: string[];
  op_kinds: string[];
  conditions: PolicyRuleCondition[];
  condition_expr: string | null;
  trace_clause: Record<string, unknown> | null;
  priority: number;
  reason: string;
  source: 'manual' | 'compiled';
  source_text: string | null;
  status: 'active' | 'disabled';
  created_at: string;
  updated_at: string | null;
}

export interface PolicyList { items: PolicyRule[]; active_count: number; total: number }

export interface PolicyCompileResult { status: 'preview' | 'applied'; rule: PolicyRule }
