import type { ScreenKey, ScreenConfig } from '../lib/types';
import { ExploreMain, ExploreAside } from './Explore';
import { LiveMain, LiveAside } from './Live';
import { ChatMain, ChatAside } from './Chat';
import { FlowMain, FlowAside } from './Flow';
import { OpsMain, OpsAside } from './Ops';
import { AuditMain, AuditAside } from './Audit';
import { PluginsMain, PluginsAside } from './Plugins';

export const SCREENS: Record<ScreenKey, ScreenConfig> = {
  explore: {
    title: '数据源管理',
    sub: '挂载企业系统 · 自主探索生成 Operation Registry',
    actions: [['refresh', '增量更新', ''], ['play', '开始探索', 'pri']],
    tree: ['数据源 Sources', 'CodeExplorer', 'DatabaseExplorer', 'APIExplorer', 'AdminPanelExplorer', 'DocExplorer'],
    treeIc: ['chevd', 'code', 'db', 'globe', 'table', 'doc'],
    treeOn: 1,
    asideW: 280,
    Main: ExploreMain,
    Aside: ExploreAside,
  },
  live: {
    title: 'Explorer · 实时探索',
    sub: 'CodeExplorer 正在阅读 company/backend',
    prog: 73,
    tree: ['探索进程', 'Phase 1 · 全局认知', 'Phase 2 · 深度探索', 'Phase 3 · 操作生成', 'Phase 4 · 能力标注'],
    treeIc: ['pulse', 'check', 'refresh', 'sliders', 'shield'],
    treeOn: 2,
    asideW: 300,
    Main: LiveMain,
    Aside: LiveAside,
  },
  chat: {
    title: '张伟退款加急',
    sub: '自然语言操作 · 写操作执行前确认',
    tree: ['会话 Sessions', '张伟退款加急', 'Q3 报表导出', '封禁违规账号'],
    treeIc: ['chat', 'chevron', 'chevron', 'chevron'],
    treeOn: 1,
    asideW: 320,
    Main: ChatMain,
    Aside: ChatAside,
  },
  flow: {
    title: '数据流图',
    sub: 'trace: abc123 · 5 节点 · 4 边',
    actions: [['eye', '展开全部', ''], ['doc', '导出审计', '']],
    tree: ['数据流 traces', 'abc123 张伟退款', 'de45f6 报表导出', '78ghij 账号封禁'],
    treeIc: ['flow', 'chevron', 'chevron', 'chevron'],
    treeOn: 1,
    asideW: 268,
    Main: FlowMain,
    Aside: FlowAside,
  },
  ops: {
    title: '操作管理 · Operation Registry',
    sub: '8 个写操作待审核',
    actions: [['check', '批量批准', 'pri']],
    tree: ['全部 (23)', '待审核 (8)', 'query · active', 'mutation', '已禁用'],
    treeIc: ['sliders', 'refresh', 'check', 'bolt', 'x'],
    treeOn: 1,
    asideW: 320,
    Main: OpsMain,
    Aside: OpsAside,
  },
  audit: {
    title: '审计链 · trace abc123',
    sub: '8 事件 · hash 链 · 完整性已验证',
    actions: [['doc', '导出', '']],
    tree: ['全部 traces', 'abc123 张伟退款', 'de45f6 报表导出', '78ghij 账号封禁'],
    treeIc: ['shield', 'chevron', 'chevron', 'chevron'],
    treeOn: 1,
    asideW: 300,
    Main: AuditMain,
    Aside: AuditAside,
  },
  plugins: {
    title: '插件中心 · Extensibility',
    sub: '5 个稳定接口 · 实现即接入，内核不变',
    tree: ['全部接口', 'Explorer', 'Executor', 'PolicyEngine', 'AuditSink', 'LLMAdapter'],
    treeIc: ['puzzle', 'compass', 'bolt', 'shield', 'doc', 'code'],
    treeOn: 0,
    asideW: 300,
    Main: PluginsMain,
    Aside: PluginsAside,
  },
};
