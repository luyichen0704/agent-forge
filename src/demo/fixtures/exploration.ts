/** Demo exploration SSE event script — ~26 events, 4 phases, ~15s total */

export interface ExplorationEventScript {
  type: string;
  payload: Record<string, unknown>;
  delayMs: number;
}

export const EXPLORATION_EVENTS: ExplorationEventScript[] = [
  // Phase 1: 全局认知
  { type: 'phase', payload: { phase: 1, label: '全局认知', description: '扫描代码库结构' }, delayMs: 300 },
  { type: 'file', payload: { path: 'src/api/http.ts', size: 1240, lang: 'typescript' }, delayMs: 400 },
  { type: 'file', payload: { path: 'src/features/auth.ts', size: 890, lang: 'typescript' }, delayMs: 350 },
  { type: 'file', payload: { path: 'server/app/api/chat.py', size: 2100, lang: 'python' }, delayMs: 500 },
  { type: 'file', payload: { path: 'server/app/models/__init__.py', size: 3400, lang: 'python' }, delayMs: 420 },
  { type: 'rule', payload: { id: 'r-001', type: 'auth_required', text: '所有 API 需要 Bearer token', confidence: 0.95 }, delayMs: 600 },
  { type: 'rule', payload: { id: 'r-002', type: 'rbac', text: '角色限制屏幕访问', confidence: 0.92 }, delayMs: 500 },
  // Phase 2: 深度探索
  { type: 'phase', payload: { phase: 2, label: '深度探索', description: '分析业务逻辑与数据流' }, delayMs: 1200 },
  { type: 'file', payload: { path: 'server/app/api/operations.py', size: 1800, lang: 'python' }, delayMs: 380 },
  { type: 'file', payload: { path: 'server/app/services/executor.py', size: 2600, lang: 'python' }, delayMs: 450 },
  { type: 'extract', payload: { entity: 'Order', fields: ['id', 'status', 'amount', 'customer_id'], source: 'models' }, delayMs: 700 },
  { type: 'extract', payload: { entity: 'RefundRecord', fields: ['order_id', 'amount', 'refund_status'], source: 'models' }, delayMs: 600 },
  { type: 'extract', payload: { entity: 'Customer', fields: ['id', 'name', 'tier', 'email'], source: 'models' }, delayMs: 550 },
  { type: 'rule', payload: { id: 'r-003', type: 'write_confirm', text: 'mutation 操作需用户确认', confidence: 0.98 }, delayMs: 800 },
  { type: 'rule', payload: { id: 'r-004', type: 'scope_policy', text: 'customer 只能访问自己的数据', confidence: 0.99 }, delayMs: 750 },
  // Phase 3: 操作生成
  { type: 'phase', payload: { phase: 3, label: '操作生成', description: '从代码推断可执行操作草稿' }, delayMs: 1200 },
  { type: 'op', payload: { key: 'order.search', kind: 'query', risk: 'low', desc: '搜索订单列表（发现新）', draft: true }, delayMs: 500 },
  { type: 'op', payload: { key: 'customer.update_tier', kind: 'mutation', risk: 'medium', desc: '修改客户等级（发现新）', draft: true }, delayMs: 600 },
  { type: 'op', payload: { key: 'report.generate', kind: 'query', risk: 'low', desc: '生成业务报表（发现新）', draft: true }, delayMs: 550 },
  { type: 'chain', payload: { chain_id: 'ch-001', nodes: 3, desc: 'order→refund→notify 执行链' }, delayMs: 800 },
  { type: 'chain', payload: { chain_id: 'ch-002', nodes: 2, desc: 'customer→order 查询链' }, delayMs: 700 },
  // Phase 4: 能力标注
  { type: 'phase', payload: { phase: 4, label: '能力标注', description: '为已发现操作打 capability 标签' }, delayMs: 1200 },
  { type: 'message', payload: { text: '标注完成：3 个新操作草稿，2 个活跃查询，ready for review' }, delayMs: 600 },
  { type: 'op', payload: { key: 'order.search', kind: 'query', risk: 'low', status: 'active', cap: 'data' }, delayMs: 400 },
  { type: 'op', payload: { key: 'report.generate', kind: 'query', risk: 'low', status: 'active', cap: 'data' }, delayMs: 350 },
  { type: 'done', payload: { operations: 5, total_rules: 4, total_entities: 3, total_chains: 2 }, delayMs: 500 },
];
