import type { ScreenKey } from '../../api/types';

export interface NavDescItem {
  desc: string;
  step?: 1 | 2 | 3;
  stepLabel?: string;
}

export const NAV_DESC: Record<ScreenKey, NavDescItem> = {
  explore: {
    desc: '挂载企业系统数据源，P-LLM 自动探索生成操作注册表',
    step: 1,
    stepLabel: '接入探索',
  },
  live: {
    desc: '实时查看 P-LLM 驱动的探索事件流与阶段进度',
    step: 1,
    stepLabel: '接入探索',
  },
  chat: {
    desc: '用自然语言下达指令，P-LLM 生成可审计的执行计划',
    step: 2,
    stepLabel: '对话执行',
  },
  flow: {
    desc: '查看执行计划的能力标注数据流图，理解信息流转路径',
    step: 2,
    stepLabel: '对话执行',
  },
  ops: {
    desc: '管理操作注册表：审核写操作、配置权限与确认级别',
    step: 3,
    stepLabel: '治理审计',
  },
  audit: {
    desc: '查看不可篡改的 hash 链审计记录，支持操作回滚',
    step: 3,
    stepLabel: '治理审计',
  },
  plugins: {
    desc: '通过稳定接口接入扩展能力：Explorer / Executor / PolicyEngine 等',
  },
};

export const WORKFLOW_STEPS = ['接入探索', '对话执行', '治理审计'] as const;

export const STEP_BADGES: Record<1 | 2 | 3, string> = {
  1: '①',
  2: '②',
  3: '③',
};
