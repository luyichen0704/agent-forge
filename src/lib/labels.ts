/* 集中术语映射表 —— 把面向用户的技术黑话统一翻译成业务语言。
 *
 * 产品面向的是各行业领域专家（财务/HR/运营/客服），不是程序员。所有用户可见的
 * 技术术语都在这里翻译，组件不再散落硬编码。技术标识（op_key、事件英文名等）可以
 * 保留在次要/弱化位置（如副标题），但主标题一律是人话。
 *
 * 说明：这里只做「展示层」翻译，不改任何后端字段名、请求或数据结构。
 */
import type { CapKind } from '../api/types';

/* ---- 审计事件类型（AuditEvent.event，服务端为准） ---- */
export const EVENT_LABEL: Record<string, string> = {
  REQUEST_RECEIVED: '收到请求',
  PLAN_GENERATED: '生成方案',
  POLICY_EVALUATED: '策略校验',
  POLICY_DENIED: '策略拦截',
  CONFIRMATION_REQUESTED: '请求确认',
  USER_CONFIRMED: '用户确认',
  DATA_READ: '读取数据',
  QLLM_PARSED: '数据解析',
  OPERATION_EXECUTED: '执行操作',
  DATAFLOW_SNAPSHOT: '数据流快照',
  RESPONSE_SENT: '返回结果',
  EXECUTION_ROLLED_BACK: '操作已回滚',
  APPROVAL_VOTE: '审批投票',
  GENESIS: '起始',
};
export const eventLabel = (e: string): string => EVENT_LABEL[e] ?? e;

/* ---- 操作类型 query / mutation ---- */
export const KIND_LABEL: Record<string, string> = { query: '查询', mutation: '修改' };
export const kindLabel = (k: string): string => KIND_LABEL[k] ?? k;

/* ---- 计划步骤类型 query / parse / write ---- */
export const STEP_KIND_LABEL: Record<string, string> = { query: '查询', parse: '解析', write: '写操作' };
export const stepKindLabel = (k: string): string => STEP_KIND_LABEL[k] ?? k;

/* ---- 确认级别 auto / confirm / dual ---- */
export const CONFIRM_LABEL: Record<string, string> = {
  auto: '自动执行', confirm: '需确认', dual: '需双人审批',
};
export const confirmLabel = (c: string): string => CONFIRM_LABEL[c] ?? c;

/* ---- 操作状态 pending / active / disabled ---- */
export const OP_STATUS_LABEL: Record<string, string> = {
  pending: '待审核', active: '已上线', disabled: '已停用',
};
export const opStatusLabel = (s: string): string => OP_STATUS_LABEL[s] ?? s;

/* ---- 执行状态 ---- */
export const EXEC_STATUS_LABEL: Record<string, string> = {
  ok: '成功', rolled_back: '已回滚', error: '失败', failed: '失败', pending: '进行中',
};
export const execStatusLabel = (s: string): string => EXEC_STATUS_LABEL[s] ?? s;

/* ---- 审批状态 ---- */
export const APPROVAL_STATUS_LABEL: Record<string, string> = {
  pending: '待审批', approved: '已批准', rejected: '已拒绝', expired: '已过期',
};
export const approvalStatusLabel = (s: string): string => APPROVAL_STATUS_LABEL[s] ?? s;

/* ---- 权限标签 all / emp+ / admin ---- */
export const PERM_LABEL: Record<string, string> = {
  all: '所有人', 'emp+': '员工及以上', admin: '仅管理员',
};
export const permLabel = (p: string): string => PERM_LABEL[p] ?? p;

/* ---- 风险等级 ---- */
export const RISK_LABEL: Record<string, string> = {
  low: '低', medium: '中', high: '高', critical: '极高',
};
export const riskLabel = (r: string): string => RISK_LABEL[r] ?? r;

/* ---- 数据能力（来源标注） ---- */
export const CAP_LABEL: Record<CapKind | string, string> = {
  trusted: '可信输入', data: '内部数据', parsed: '解析结果', write: '写操作',
};
export const capLabel = (c: string): string => CAP_LABEL[c] ?? c;

/* ---- 探索器类名 → 中文别名 ---- */
export const EXPLORER_LABEL: Record<string, string> = {
  CodeExplorer: '代码探索器',
  DatabaseExplorer: '数据库探索器',
  APIExplorer: '接口探索器',
  AdminPanelExplorer: '后台探索器',
  DocExplorer: '文档探索器',
};
export const explorerLabel = (k: string): string => EXPLORER_LABEL[k] ?? k;

/* ---- 数据源类型 ---- */
export const SRC_TYPE_LABEL: Record<string, string> = {
  code: '代码库', db: '数据库', api: '接口', admin: '管理后台', doc: '文档',
};

/* ---- 数据源状态 ---- */
export const SRC_STATUS_LABEL: Record<string, string> = {
  connected: '已连接', running: '探索中', disconnected: '未连接', error: '连接异常',
};
export const srcStatusLabel = (s: string): string => SRC_STATUS_LABEL[s] ?? s;

/* ---- 插件接口 → 中文功能名 ---- */
export const IFACE_LABEL: Record<string, string> = {
  Explorer: '数据源探索器',
  Executor: '操作执行器',
  PolicyEngine: '策略引擎',
  AuditSink: '审计记录',
  LLMAdapter: 'AI 模型接入',
};
export const ifaceLabel = (i: string): string => IFACE_LABEL[i] ?? i;

/* ---- 模型角色 pllm / qllm ---- */
export const LLM_ROLE_LABEL: Record<string, string> = {
  pllm: '规划模型', qllm: '解析模型',
};
export const llmRoleLabel = (r: string): string => LLM_ROLE_LABEL[r] ?? r;

/* ---- 执行器绑定（隐藏内部实现名） ---- */
export const EXECUTOR_LABEL: Record<string, string> = {
  FunctionExecutor: '内置执行',
  APIExecutor: '接口执行',
  SQLExecutor: '数据库执行',
  RPAExecutor: '流程执行',
};
export const executorLabel = (e?: string | null): string => (e ? EXECUTOR_LABEL[e] ?? '系统执行' : '系统执行');

/* ---- 插件实现名（类名）→ 业务别名。技术类名下沉为副标题。 ---- */
export const IMPL_LABEL: Record<string, string> = {
  CodeExplorer: '代码库探索', DatabaseExplorer: '数据库探索', APIExplorer: '接口探索',
  AdminPanelExplorer: '后台探索', DocExplorer: '文档探索',
  APIExecutor: '接口执行', FunctionExecutor: '内置执行', SQLExecutor: '数据库执行', RPAExecutor: '流程执行',
  PythonPolicyEngine: '内置策略引擎', OPAPolicyEngine: 'OPA 策略引擎', CasbinPolicyEngine: 'Casbin 策略引擎',
  PostgresAuditSink: '数据库审计存储', S3AuditSink: '对象存储审计', ElasticAuditSink: '检索型审计存储',
};
/** 保留 " · 角色" 后缀（如 "AnthropicAdapter · P-LLM"）并翻译模型代号。 */
export function implLabel(name: string): string {
  const [head, ...restParts] = name.split('·').map((s) => s.trim());
  const rest = restParts.join(' · ')
    .replace(/P-LLM/gi, '规划模型').replace(/Q-LLM/gi, '解析模型');
  const mapped = IMPL_LABEL[head] ?? head;
  return rest ? `${mapped} · ${rest}` : mapped;
}

/* ---- 实时探索事件前缀 ---- */
export const STREAM_LABEL: Record<string, string> = {
  phase: '阶段', op: '发现操作', rule: '业务规则', done: '完成',
  file: '扫描文件', extract: '提取', chain: '关联', error: '出错', message: '进度',
};
export const streamLabel = (t: string): string => STREAM_LABEL[t] ?? t;

/* ---- 数据流节点来源类型 ---- */
export const NODE_SOURCE_LABEL: Record<string, string> = {
  user: '用户输入', query: '查询', parse: '解析', write: '写操作',
};
export const nodeSourceLabel = (s: string): string => NODE_SOURCE_LABEL[s] ?? s;

/* ---- 常见 op_key 的业务名（种子操作；探索发现的操作自带 desc） ---- */
export const OP_KEY_LABEL: Record<string, string> = {
  'order.query': '查询订单',
  'order.cancel': '取消订单',
  'customer.query': '查询客户',
  'refund.expedite': '加急退款',
  'refund.query': '查询退款',
  'user.ban': '封禁用户',
  'hr.salary_set': '调整薪资',
};

/** 操作的业务标题：优先用服务端 desc，其次已知 op_key 业务名，最后回退原始 key。 */
export function opTitle(o: { desc?: string | null; op_key: string }): string {
  const d = o.desc?.trim();
  if (d) return d;
  const base = o.op_key.replace(/\.rollback$/, '');
  const named = OP_KEY_LABEL[base];
  if (named) return o.op_key.endsWith('.rollback') ? `${named}（回滚）` : named;
  return o.op_key;
}

/** 把数据流节点标签转成业务语言（去掉 user_input(...) 与模型代号）。 */
export function flowNodeLabel(label: string): string {
  const m = label.match(/^user_input\("?(.*?)"?\)$/);
  if (m) return `你的输入：${m[1]}`;
  return label.replace(/Q-LLM/g, '解析模型').replace(/P-LLM/g, '规划模型');
}

/* ---- 审计事件详情（payload）人话化：翻译字段名、隐藏技术 id ---- */
const PAYLOAD_KEY_LABEL: Record<string, string> = {
  role: '角色', instruction: '指令', intent: '意图', steps: '步骤数',
  op: '操作', reason: '原因', required_confirm: '需确认级别', level: '确认级别',
  writes: '写操作数', eligible_admins: '可审批人数', approver: '审批人',
  status: '状态', rows: '数据条数', error: '错误', selected: '命中数',
  capability: '数据类型', executor: '执行方式', latency_ms: '耗时(ms)', target: '目标',
};
// 技术标识，不下发到用户视图
const PAYLOAD_HIDE = new Set(['llm_run_id']);
const PAYLOAD_STATUS_LABEL: Record<string, string> = {
  done: '完成', partial_failed: '部分失败', ok: '成功', partial: '部分完成',
};

function fmtPayloadVal(key: string, v: unknown): string {
  const s = String(v);
  if (key === 'op' || key === 'target') return OP_KEY_LABEL[s] ?? s;
  if (key === 'capability') return capLabel(s);
  if (key === 'executor') return executorLabel(s);
  if (key === 'required_confirm' || key === 'level') return confirmLabel(s);
  if (key === 'status') return PAYLOAD_STATUS_LABEL[s] ?? execStatusLabel(s);
  return s;
}

/** 把审计事件的 payload 渲染成一行人话摘要（隐藏 llm_run_id 等技术 id）。 */
export function auditPayloadSummary(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(payload)) {
    if (PAYLOAD_HIDE.has(k) || v == null || v === '') continue;
    if (typeof v === 'object') continue; // 跳过嵌套结构，保持一行简洁
    parts.push(`${PAYLOAD_KEY_LABEL[k] ?? k}：${fmtPayloadVal(k, v)}`);
  }
  return parts.join(' · ');
}
