/** Demo plugin fixtures from server/app/seed.py PLUGINS */
import type { Plugin } from '../../api/types';

export const DEMO_PLUGINS: Plugin[] = [
  {
    id: 'pl-explorer', iface: 'Explorer', sub: '数据源探索', icon: 'compass',
    code: 'class Explorer(ABC):\n  async def explore(self, src) -> list[OperationDraft]',
    impls: [
      { name: 'CodeExplorer', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'DatabaseExplorer', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'APIExplorer', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'AdminPanelExplorer', status: 'wait', version: '0.9', health: 'unknown' },
      { name: 'DocExplorer', status: 'ok', version: '1.0', health: 'ok' },
    ],
  },
  {
    id: 'pl-executor', iface: 'Executor', sub: '执行后端 · 按优先级 fallback', icon: 'bolt',
    code: 'class Executor(ABC):\n  async def execute(op, params)\n  async def rollback(exec_id)',
    impls: [
      { name: 'APIExecutor', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'FunctionExecutor', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'SQLExecutor', status: 'wait', version: '0.8', health: 'unknown' },
      { name: 'RPAExecutor', status: 'wait', version: '0.5', health: 'unknown' },
    ],
  },
  {
    id: 'pl-policy', iface: 'PolicyEngine', sub: '策略判定', icon: 'shield',
    code: 'class PolicyEngine(ABC):\n  def evaluate(identity, op, kwargs, dataflow) -> Decision',
    impls: [
      { name: 'PythonPolicyEngine', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'OPAPolicyEngine', status: 'off', version: '0.1', health: 'unknown' },
      { name: 'CasbinPolicyEngine', status: 'off', version: '0.1', health: 'unknown' },
    ],
  },
  {
    id: 'pl-audit', iface: 'AuditSink', sub: '审计后端', icon: 'doc',
    code: 'class AuditSink(ABC):\n  async def write(record)\n  async def query(range)',
    impls: [
      { name: 'PostgresAuditSink', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'S3AuditSink', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'ElasticAuditSink', status: 'off', version: '0.3', health: 'unknown' },
    ],
  },
  {
    id: 'pl-llm', iface: 'LLMAdapter', sub: '模型接入', icon: 'code',
    code: 'class LLMAdapter(ABC):\n  def chat(msgs)\n  def structured_output(schema)',
    impls: [
      { name: 'AnthropicAdapter · P-LLM', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'LocalQwen · Q-LLM', status: 'ok', version: '1.0', health: 'ok' },
      { name: 'OpenAIAdapter', status: 'off', version: '0.2', health: 'unknown' },
    ],
  },
];
