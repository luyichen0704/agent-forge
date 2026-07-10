import type { ScreenKey } from '../../api/types';

export interface NavDescItem {
  desc: string;
  step?: 1 | 2 | 3;
  stepLabel?: string;
}

export const NAV_DESC: Record<ScreenKey, NavDescItem> = {
  explore: {
    desc: '挂载企业系统数据源，系统自动发现其中可用的操作',
    step: 1,
    stepLabel: '接入探索',
  },
  live: {
    desc: '实时查看探索进展与各阶段进度',
    step: 1,
    stepLabel: '接入探索',
  },
  chat: {
    desc: '用自然语言下达指令，系统生成可审计的执行计划',
    step: 2,
    stepLabel: '对话执行',
  },
  flow: {
    desc: '查看执行计划的数据流向图，理解信息如何流转',
    step: 2,
    stepLabel: '对话执行',
  },
  ops: {
    desc: '管理可执行操作：审核写操作、配置权限与确认级别',
    step: 3,
    stepLabel: '治理审计',
  },
  audit: {
    desc: '查看完整不可篡改的操作记录，支持一键回滚',
    step: 3,
    stepLabel: '治理审计',
  },
  plugins: {
    desc: '通过标准接口接入扩展能力：数据源探索器、执行器、策略引擎等',
  },
};

export const WORKFLOW_STEPS = ['接入探索', '对话执行', '治理审计'] as const;

export const STEP_BADGES: Record<1 | 2 | 3, string> = {
  1: '①',
  2: '②',
  3: '③',
};
