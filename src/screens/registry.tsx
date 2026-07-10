import type { ScreenKey } from '../api/types';
import { ExploreMain, ExploreAside } from './Explore';
import { LiveMain, LiveAside } from './Live';
import { ChatMain, ChatAside } from './Chat';
import { FlowMain, FlowAside } from './Flow';
import { OpsMain, OpsAside } from './Ops';
import { AuditMain, AuditAside } from './Audit';
import { PluginsMain, PluginsAside } from './Plugins';

export interface ScreenConfig {
  title: string;
  sub: string;
  asideW: number;
  tree: string[];
  treeIc: string[];
  Main: () => React.ReactElement;
  Aside: () => React.ReactElement;
}

export const SCREENS: Record<ScreenKey, ScreenConfig> = {
  explore: {
    title: '数据源管理',
    sub: '挂载企业系统 · 自动发现可用操作',
    tree: ['全部数据源', '代码库', '数据库', '接口', '管理后台', '文档'],
    treeIc: ['chevd', 'code', 'db', 'globe', 'table', 'doc'],
    asideW: 280, Main: ExploreMain, Aside: ExploreAside,
  },
  live: {
    title: '实时探索',
    sub: '探索任务的实时进展',
    tree: ['探索进程', '阶段 1 · 全局认知', '阶段 2 · 深度探索', '阶段 3 · 操作生成', '阶段 4 · 能力标注'],
    treeIc: ['pulse', 'check', 'refresh', 'sliders', 'shield'],
    asideW: 300, Main: LiveMain, Aside: LiveAside,
  },
  chat: {
    title: '对话',
    sub: '自然语言操作 · 写操作执行前确认',
    tree: ['会话记录'],
    treeIc: ['chat'],
    asideW: 320, Main: ChatMain, Aside: ChatAside,
  },
  flow: {
    title: '数据流图',
    sub: '数据流向 · 与执行计划一致',
    tree: ['全部数据流'],
    treeIc: ['flow'],
    asideW: 268, Main: FlowMain, Aside: FlowAside,
  },
  ops: {
    title: '操作管理',
    sub: '管理可执行操作 · 权限与审核',
    tree: ['全部', '待审核', '查询（已上线）', '修改', '已停用'],
    treeIc: ['sliders', 'refresh', 'check', 'bolt', 'x'],
    asideW: 320, Main: OpsMain, Aside: OpsAside,
  },
  audit: {
    title: '审计记录',
    sub: '完整不可篡改 · 可验证',
    tree: ['全部记录'],
    treeIc: ['shield'],
    asideW: 300, Main: AuditMain, Aside: AuditAside,
  },
  plugins: {
    title: '扩展中心',
    sub: '标准接口 · 接入即用，无需改动核心',
    tree: ['全部', '数据源探索器', '操作执行器', '策略引擎', '审计记录', 'AI 模型接入'],
    treeIc: ['puzzle', 'compass', 'bolt', 'shield', 'doc', 'code'],
    asideW: 300, Main: PluginsMain, Aside: PluginsAside,
  },
};
