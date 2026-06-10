import type { ScreenKey } from '../api/types';

export type Placement = 'right' | 'left' | 'top' | 'bottom' | 'center';
export type Advance = 'next' | 'click';

export interface TourStep {
  id: string;
  screen?: ScreenKey;
  target: string;
  title: string;
  body: string;
  advance: Advance;
  waitForTarget?: boolean;
  placement?: Placement;
  fill?: string;
  onEnter?: () => void;
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: 'rail-overview',
    target: '[data-tour="rail"]',
    title: '① 欢迎使用 agent·forge',
    body: '这是活动导航栏。左侧图标分三个 Step：① 接入探索 · ② 对话执行 · ③ 治理审计。接下来我们按真实业务流程走一遍，约 3 分钟。',
    advance: 'next',
    placement: 'right',
  },
  {
    id: 'chat-input',
    screen: 'chat',
    target: '[data-tour="chat-input"]',
    title: '② 用自然语言下达指令',
    body: '在这里用中文输入业务指令。P-LLM 会把它转成结构化执行计划，每一步都标注数据能力。点击「填入示例指令」试试。',
    advance: 'next',
    placement: 'top',
    fill: '查一下张伟的退款单，把还在 pending 的加急处理',
  },
  {
    id: 'chat-send',
    screen: 'chat',
    target: '[data-tour="chat-send"]',
    title: '③ 发送指令',
    body: '点击「发送」按钮（或按 Enter），P-LLM 开始规划。规划完成后，右侧会出现执行计划卡片。',
    advance: 'click',
    placement: 'top',
  },
  {
    id: 'plan-card',
    screen: 'chat',
    target: '[data-tour="plan-card"]',
    title: '④ 查看执行计划',
    body: 'P-LLM 生成了结构化计划：每个步骤都标注了数据能力（query/mutation/parse），写操作清晰可见。右侧面板展示了意图与能力细节。',
    advance: 'next',
    waitForTarget: true,
    placement: 'left',
  },
  {
    id: 'plan-aside',
    screen: 'chat',
    target: '[data-tour="chat-aside"]',
    title: '⑤ P-LLM 计划详情',
    body: 'P-LLM 只生成计划，看不到具体业务数据。写操作必须经过策略审查与人工确认才能执行——这是 CaMeL 架构的核心保障。',
    advance: 'next',
    placement: 'left',
  },
  {
    id: 'plan-confirm',
    screen: 'chat',
    target: '[data-tour="plan-confirm"]',
    title: '⑥ 确认执行写操作',
    body: '出现「确认执行」按钮了！写操作需要人工确认。点击它，P-LLM 计划将在策略引擎验证后写入审计链。',
    advance: 'click',
    waitForTarget: true,
    placement: 'top',
  },
  {
    id: 'plan-done',
    screen: 'chat',
    target: '[data-tour="plan-done"]',
    title: '⑦ 已执行 · 已写入审计链',
    body: '操作完成！每次写操作都会生成一条哈希链记录，不可篡改。点击「查看审计」可定位到这次执行。',
    advance: 'next',
    waitForTarget: true,
    placement: 'top',
  },
  {
    id: 'flow-graph',
    screen: 'flow',
    target: '[data-tour="flow-graph"]',
    title: '⑧ 数据流图',
    body: 'Flow 视图展示了这次执行的数据流向与能力标注。Q-LLM 的输出继承输入能力——信息无法被"洗白"成可信，这是防篡改的关键。',
    advance: 'next',
    placement: 'right',
  },
  {
    id: 'audit-chain',
    screen: 'audit',
    target: '[data-tour="audit-chain"]',
    title: '⑨ 审计链 · hash 不可篡改',
    body: '每个操作事件都有 hash，与上一事件链式连接。系统自动验证链的完整性——任何篡改都会被检测出来。',
    advance: 'next',
    placement: 'right',
  },
  {
    id: 'audit-rollback',
    screen: 'audit',
    target: '[data-tour="audit-rollback"]',
    title: '⑩ 回滚操作',
    body: '右侧面板展示执行的 before/after 快照，可以一键回滚写操作。补偿事件也会写入审计链，保持完整记录。',
    advance: 'next',
    placement: 'left',
  },
  {
    id: 'ops-table',
    screen: 'ops',
    target: '[data-tour="ops-table"]',
    title: '⑪ 操作注册表',
    body: '所有由探索器发现的操作都在这里管理：状态、权限、确认级别、执行器绑定，一目了然。写操作默认待审核。',
    advance: 'next',
    placement: 'top',
  },
  {
    id: 'ops-approvals',
    screen: 'ops',
    target: '[data-tour="ops-approvals"]',
    title: '⑫ 双人审批',
    body: '高风险写操作（dual_approval）需要两名审批人各自批准。这是真实的多人审批流程，每次投票都记录在审计链中。',
    advance: 'next',
    placement: 'top',
  },
  {
    id: 'explore-start',
    screen: 'explore',
    target: '[data-tour="explore-start"]',
    title: '⑬ 探索数据源',
    body: '点击「开始探索」，P-LLM 会真实读取数据源连接信息，自动发现操作，写入注册表。整个过程可在「实时探索」屏中实时观察。',
    advance: 'click',
    placement: 'left',
  },
  {
    id: 'live-log',
    screen: 'live',
    target: '[data-tour="live-log"]',
    title: '⑭ 实时事件流',
    body: '这里是 P-LLM 驱动探索的实时 SSE 流。每发现一个操作（op）、规则（rule）或进入新阶段（phase），都会立即出现在这里。',
    advance: 'next',
    waitForTarget: true,
    placement: 'top',
  },
  {
    id: 'plugins-grid',
    screen: 'plugins',
    target: '[data-tour="plugins-grid"]',
    title: '⑮ 插件接口',
    body: 'CaMeL 的每个能力都通过稳定接口暴露：Explorer / Executor / PolicyEngine / AuditSink / LLMAdapter。接入新实现无需改内核。',
    advance: 'next',
    placement: 'right',
  },
  {
    id: 'role-switch',
    screen: 'chat',
    target: '[data-tour="role-switch"]',
    title: '⑯ 身份切换',
    body: '切换身份体验权限差异：客户只能对话，员工可查看操作与审计，管理员拥有全部权限。每个角色的可见功能都不同。',
    advance: 'next',
    placement: 'right',
  },
  {
    id: 'tour-done',
    target: 'body',
    title: '教程完成 🎉',
    body: '你已走完完整的业务流程！需要再看一遍，点左下角 ? 按钮随时重开。左下角齿轮菜单也可以重开总览或退出登录。',
    advance: 'next',
    placement: 'center',
  },
];

export const TOUR_TOTAL = TOUR_STEPS.length;
