/* ============================================================
   CaMeL-Business · centralized demo data
   All screens import from here — never inline demo data.
   ============================================================ */

import type {
  NavItem, ScreenKey, Role, Operation, FlowNode,
  AuditEvent, DataSource, ExplorePhase, ChatPlan, Plugin
} from './types';

/* ---- nav model ---- */
export const NAV: NavItem[] = [
  { k: 'explore', cn: '探索配置', en: 'Explore', ic: 'compass' },
  { k: 'live',    cn: '实时探索', en: 'Live',    ic: 'pulse'   },
  { k: 'chat',    cn: '对话',     en: 'Chat',    ic: 'chat'    },
  { k: 'flow',    cn: '数据流',   en: 'Flow',    ic: 'flow'    },
  { k: 'ops',     cn: '操作管理', en: 'Ops',     ic: 'sliders' },
  { k: 'audit',   cn: '审计',     en: 'Audit',   ic: 'shield'  },
  { k: 'plugins', cn: '插件',     en: 'Plugins', ic: 'puzzle'  },
];

/* ---- role → allowed screens ---- */
export const ROLE_NAV: Record<Role, ScreenKey[]> = {
  customer: ['chat', 'flow'],
  employee: ['chat', 'flow', 'live', 'ops'],
  admin:    ['explore', 'live', 'chat', 'flow', 'ops', 'audit', 'plugins'],
};

/* ---- data sources (Explore screen) ---- */
export const DATA_SOURCES: DataSource[] = [
  { icon: 'code',  label: '源代码',   conn: 'GitHub · company/backend',   statusLabel: '已探索 · 142 files', dotKind: 'ok'   },
  { icon: 'db',    label: '数据库',   conn: 'PostgreSQL · prod-db',        statusLabel: '已映射 · 34 表',     dotKind: 'ok'   },
  { icon: 'globe', label: 'API',      conn: 'OpenAPI · /api/v1/docs',      statusLabel: '已解析 · 47 路由',   dotKind: 'ok'   },
  { icon: 'table', label: '管理后台', conn: 'admin.company.com',           statusLabel: '爬取中 · 45%',       dotKind: 'wait', progress: 45 },
  { icon: 'doc',   label: '文档',     conn: 'Confluence · Engineering',    statusLabel: '已索引 · 128 页',    dotKind: 'ok'   },
];

/* ---- explore phases ---- */
export const EXPLORE_PHASES: ExplorePhase[] = [
  { label: 'Phase 1', sub: '全局认知', state: 'done' },
  { label: 'Phase 2', sub: '深度探索', state: 'now'  },
  { label: 'Phase 3', sub: '操作生成', state: 'todo' },
  { label: 'Phase 4', sub: '能力标注', state: 'todo' },
];

/* ---- live log lines ---- */
export const LIVE_FILES = [
  'src/api/orders.py',
  'src/models/order.py',
  'src/services/refund.py',
  'src/services/order.py',
];

export const LIVE_LOG = `[12:04:31] extract order.py → entity Order, OrderItem
[12:04:33] rule    取消订单需校验 refund_status
[12:04:34] chain   order.cancel → inventory.restore + refund.create
[12:04:36] + op    order.cancel  // mutation · pending_review`;

/* ---- live extraction summary ---- */
export const LIVE_EXTRACTION = [
  ['实体 Entity',  'Order, OrderItem, Refund'  ],
  ['操作 Ops',     'create · cancel · query'   ],
  ['规则 Rule',    '取消需检查退款条件'           ],
  ['联动 Chain',   'cancel → 恢复库存 + 退款'   ],
];

/* ---- chat plan per role ---- */
export const CHAT: Record<Role, ChatPlan> = {
  customer: {
    q: '查我订单 #3901 的退款进度，能不能加急？',
    note: '已自动注入 user_id = 你本人 · 看不到他人数据',
    plan: [
      ['1', '查询我的订单 #3901', 'q'],
      ['2', '查看退款状态',       'q'],
      ['3', '申请退款加急',       'm'],
    ],
    writes: 1,
    foot: '订单 #3901 退款 ¥299 · 仅本人',
    done: '已为订单 #3901 提交加急申请，预计 24h 内处理，结果会通知你。',
  },
  employee: {
    q: '帮我查张伟退货订单，把 pending 的退款加急',
    note: null,
    plan: [
      ['1', '查询客户「张伟」',       'q'],
      ['2', '查询其上月订单',          'q'],
      ['3', '筛选退货订单 · Q-LLM',   'p'],
      ['4', '对 pending 退款执行加急', 'm'],
      ['5', '通知客户',               'm'],
    ],
    writes: 2,
    foot: '订单 #3901 退款 ¥299 → 加急 · 通知张伟',
    done: '已执行完成 — 订单 #3901 退款已加急，已通知张伟。可在审计里回滚。',
  },
  admin: {
    q: '帮我查张伟退货订单，把 pending 的退款加急',
    note: null,
    plan: [
      ['1', '查询客户「张伟」',       'q'],
      ['2', '查询其上月订单',          'q'],
      ['3', '筛选退货订单 · Q-LLM',   'p'],
      ['4', '对 pending 退款执行加急', 'm'],
      ['5', '通知客户',               'm'],
    ],
    writes: 2,
    foot: '订单 #3901 退款 ¥299 → 加急 · 通知张伟',
    done: '已执行完成 — 订单 #3901 退款已加急，已通知张伟。可在审计里回滚。',
  },
};

/* ---- P-LLM code per role ---- */
export const PLLLM_CODE: Record<Role, Array<{ text: string; cls?: string }>> = {
  customer: [
    { text: 'order = ' },
    { text: 'order_query', cls: 'f' },
    { text: '(\n  order_id=' },
    { text: '"#3901"', cls: 's' },
    { text: ')\n  ' },
    { text: '# Policy 强制注入:', cls: 'c' },
    { text: '\n  ' },
    { text: '# user_id = self', cls: 'c' },
    { text: '\n' },
    { text: 'expedite_refund', cls: 'f' },
    { text: '(\n  order_id=order.id)' },
  ],
  employee: [
    { text: 'customer = ' },
    { text: 'customer_query', cls: 'f' },
    { text: '(name=' },
    { text: '"张伟"', cls: 's' },
    { text: ')\norders = ' },
    { text: 'order_query', cls: 'f' },
    { text: '(\n  user_id=customer.id,\n  date_range=' },
    { text: '"last_month"', cls: 's' },
    { text: ')\nrefunds = ' },
    { text: 'query_quarantined_llm', cls: 'f' },
    { text: '(\n  ' },
    { text: '"找出退货订单"', cls: 's' },
    { text: ', data=orders)\n' },
    { text: 'for', cls: 'k' },
    { text: ' o ' },
    { text: 'in', cls: 'k' },
    { text: ' refunds:\n  ' },
    { text: 'if', cls: 'k' },
    { text: ' o.status==' },
    { text: '"pending"', cls: 's' },
    { text: ':\n    ' },
    { text: 'expedite_refund', cls: 'f' },
    { text: '(order_id=o.id)' },
  ],
  admin: [
    { text: 'customer = ' },
    { text: 'customer_query', cls: 'f' },
    { text: '(name=' },
    { text: '"张伟"', cls: 's' },
    { text: ')\norders = ' },
    { text: 'order_query', cls: 'f' },
    { text: '(\n  user_id=customer.id,\n  date_range=' },
    { text: '"last_month"', cls: 's' },
    { text: ')\nrefunds = ' },
    { text: 'query_quarantined_llm', cls: 'f' },
    { text: '(\n  ' },
    { text: '"找出退货订单"', cls: 's' },
    { text: ', data=orders)\n' },
    { text: 'for', cls: 'k' },
    { text: ' o ' },
    { text: 'in', cls: 'k' },
    { text: ' refunds:\n  ' },
    { text: 'if', cls: 'k' },
    { text: ' o.status==' },
    { text: '"pending"', cls: 's' },
    { text: ':\n    ' },
    { text: 'expedite_refund', cls: 'f' },
    { text: '(order_id=o.id)' },
  ],
};

/* ---- flow nodes ---- */
export const FLOW_NODES: FlowNode[] = [
  { cap: 'trusted', label: 'user_input("张伟")',        node: 'user_input',     source: 'employee 直接输入', readers: 'all',        via: '可信通道 · 无解析' },
  { cap: 'data',    label: 'customer_query → customer', node: 'customer',       source: 'database.customers', readers: 'emp, admin', via: 'order.query 直读' },
  { cap: 'data',    label: 'order_query → orders',      node: 'orders',         source: 'database.orders',    readers: 'emp, admin', via: 'order.query 直读' },
  { cap: 'parsed',  label: 'Q-LLM → refund_orders',    node: 'refund_orders',  source: 'database.orders',    readers: 'emp, admin', via: 'Q-LLM (无放宽)' },
  { cap: 'write',   label: 'expedite_refund → result', node: 'result',         source: 'refund.expedite',    readers: 'emp, admin', via: 'APIExecutor · 142ms' },
];

/* ---- live explorer streaming log lines (appended over time) ---- */
export const LIVE_STREAM: Array<{ t: string; tag: string; cls: string; text: string }> = [
  { t: '12:04:31', tag: 'extract', cls: 'f', text: ' order.py → entity Order, OrderItem' },
  { t: '12:04:33', tag: 'rule',    cls: 'f', text: '    取消订单需校验 refund_status' },
  { t: '12:04:34', tag: 'chain',   cls: 'f', text: '   order.cancel → inventory.restore + refund.create' },
  { t: '12:04:36', tag: '+ op',    cls: 's', text: '    order.cancel  // mutation · pending_review' },
  { t: '12:04:38', tag: 'extract', cls: 'f', text: ' refund.py → entity Refund, RefundItem' },
  { t: '12:04:40', tag: 'rule',    cls: 'f', text: '    加急需 refund_status == pending' },
  { t: '12:04:42', tag: '+ op',    cls: 's', text: '    refund.expedite  // mutation · pending_review' },
  { t: '12:04:45', tag: 'extract', cls: 'f', text: ' notify.py → channel Email, SMS' },
];

/* ---- ops operations ---- */
export const OPS: Operation[] = [
  { name: 'order.query',    type: 'q', perm: 'all',   confirm: 'auto',    status: 'active',  roles: ['customer', 'employee', 'admin'] },
  { name: 'order.cancel',   type: 'm', perm: 'emp+',  confirm: 'confirm', status: 'pending', roles: ['employee', 'admin'] },
  { name: 'refund.expedite',type: 'm', perm: 'emp+',  confirm: 'confirm', status: 'pending', roles: ['employee', 'admin'] },
  { name: 'hr.salary_set',  type: 'm', perm: 'admin', confirm: 'dual',    status: 'pending', roles: ['admin'] },
  { name: 'user.ban',       type: 'm', perm: 'admin', confirm: 'confirm', status: 'pending', roles: ['admin'] },
  { name: 'customer.query', type: 'q', perm: 'emp+',  confirm: 'auto',    status: 'active',  roles: ['employee', 'admin'] },
];

/* ---- audit events ---- */
export const AUDIT_EVENTS: AuditEvent[] = [
  { event: 'REQUEST_RECEIVED',      detail: 'employee · 张伟退款加急',      cap: 'data'    },
  { event: 'PLAN_GENERATED',        detail: 'P-LLM · 5 步计划',            cap: 'data'    },
  { event: 'POLICY_EVALUATED',      detail: 'expedite_refund · allow',     cap: 'trusted' },
  { event: 'CONFIRMATION_REQUESTED',detail: 'confirm · 2 写操作',           cap: 'parsed'  },
  { event: 'USER_CONFIRMED',        detail: 'wei@company · 12:04',         cap: 'trusted' },
  { event: 'OPERATION_EXECUTED',    detail: 'expedite_refund · 142ms',     cap: 'write'   },
  { event: 'DATAFLOW_SNAPSHOT',     detail: '5 节点 · 4 边',               cap: 'data'    },
  { event: 'RESPONSE_SENT',         detail: '1.2k tokens · 3.4s',         cap: 'data'    },
];

/* ---- plugins ---- */
export const PLUGINS: Plugin[] = [
  {
    key: 'explorer',
    iface: 'Explorer',
    sub: '数据源探索',
    ic: 'compass',
    impls: [
      ['CodeExplorer',       'ok'  ],
      ['DatabaseExplorer',   'ok'  ],
      ['APIExplorer',        'ok'  ],
      ['AdminPanelExplorer', 'wait'],
      ['DocExplorer',        'ok'  ],
    ],
    code: `class Explorer(ABC):
  async def explore(self,
    src) -> list[OperationDraft]`,
  },
  {
    key: 'executor',
    iface: 'Executor',
    sub: '执行后端 · 按优先级 fallback',
    ic: 'bolt',
    impls: [
      ['APIExecutor',      'ok'  ],
      ['FunctionExecutor', 'ok'  ],
      ['SQLExecutor',      'wait'],
      ['RPAExecutor',      'wait'],
    ],
    code: `class Executor(ABC):
  async def execute(op, params)
  async def rollback(exec_id)
  async def capture_state(...)`,
  },
  {
    key: 'policy',
    iface: 'PolicyEngine',
    sub: '策略判定',
    ic: 'shield',
    impls: [
      ['PythonPolicyEngine', 'ok' ],
      ['OPAPolicyEngine',    'off'],
      ['CasbinPolicyEngine', 'off'],
    ],
    code: `class PolicyEngine(ABC):
  def evaluate(identity, op,
    kwargs, dataflow) -> Decision`,
  },
  {
    key: 'sink',
    iface: 'AuditSink',
    sub: '审计后端',
    ic: 'doc',
    impls: [
      ['PostgresAuditSink', 'ok' ],
      ['S3AuditSink',       'ok' ],
      ['ElasticAuditSink',  'off'],
      ['SIEMAuditSink',     'off'],
    ],
    code: `class AuditSink(ABC):
  async def write(record)
  async def query(range)`,
  },
  {
    key: 'llm',
    iface: 'LLMAdapter',
    sub: '模型接入',
    ic: 'code',
    impls: [
      ['AnthropicAdapter · P-LLM', 'ok' ],
      ['LocalQwen · Q-LLM',        'ok' ],
      ['OpenAIAdapter',            'off'],
      ['vLLMAdapter',              'off'],
    ],
    code: `class LLMAdapter(ABC):
  def chat(msgs)
  def structured_output(schema)`,
  },
];
