/** Chat scenario matching logic for demo mode */
import type { Plan, PlanStep } from '../../api/types';

export type Scenario = 'A' | 'B' | 'C' | 'fallback';

/** Match user input to a demo scenario */
export function matchScenario(content: string): Scenario {
  const t = content.toLowerCase();
  if (/退款|加急|refund|expedite/.test(t)) return 'A';
  if (/薪资|工资|salary|hr/.test(t)) return 'B';
  if (/查询|订单|order|查一下/.test(t)) return 'C';
  return 'fallback';
}

/** Scenario A: employee refund expedite — 4-step plan, awaiting_confirm */
export function buildScenarioAPlan(traceId: string, planId: string): Plan {
  const steps: PlanStep[] = [
    { step_no: 1, kind: 'query', op_key: 'customer.query', label: '查询客户信息 · 张伟', capability_in: ['trusted'], capability_out: 'data', approval_request_id: null, status: 'pending' },
    { step_no: 2, kind: 'query', op_key: 'order.query', label: '查询订单/退款单', capability_in: ['data'], capability_out: 'data', approval_request_id: null, status: 'pending' },
    { step_no: 3, kind: 'parse', op_key: null, label: 'Q-LLM 解析 pending 退款单', capability_in: ['data'], capability_out: 'parsed', approval_request_id: null, status: 'pending' },
    { step_no: 4, kind: 'write', op_key: 'refund.expedite', label: '加急处理退款单 #3901', capability_in: ['parsed'], capability_out: 'write', approval_request_id: null, status: 'pending' },
  ];
  return {
    id: planId,
    trace_id: traceId,
    intent: '查询张伟退款单并加急处理 pending 退款',
    writes: 1,
    required_confirm_level: 'confirm',
    status: 'awaiting_confirm',
    reasoning_summary: '检测到 1 个写操作（refund.expedite），风险等级 high，需要用户确认后执行。',
    policy_hints: ['refund.expedite 为 high 风险 mutation，已强制 confirm 级', 'scope=self 策略已适用'],
    steps,
    blocked: false,
  };
}

/** Scenario A confirmed plan — done with trace materialized */
export function buildScenarioADonePlan(planId: string, traceId: string): Plan {
  const steps: PlanStep[] = [
    { step_no: 1, kind: 'query', op_key: 'customer.query', label: '查询客户信息 · 张伟', capability_in: ['trusted'], capability_out: 'data', approval_request_id: null, status: 'done' },
    { step_no: 2, kind: 'query', op_key: 'order.query', label: '查询订单/退款单', capability_in: ['data'], capability_out: 'data', approval_request_id: null, status: 'done' },
    { step_no: 3, kind: 'parse', op_key: null, label: 'Q-LLM 解析 pending 退款单', capability_in: ['data'], capability_out: 'parsed', approval_request_id: null, status: 'done' },
    { step_no: 4, kind: 'write', op_key: 'refund.expedite', label: '加急处理退款单 #3901', capability_in: ['parsed'], capability_out: 'write', approval_request_id: null, status: 'done' },
  ];
  return {
    id: planId,
    trace_id: traceId,
    intent: '查询张伟退款单并加急处理 pending 退款',
    writes: 1,
    required_confirm_level: 'confirm',
    status: 'done',
    reasoning_summary: '检测到 1 个写操作（refund.expedite），风险等级 high，需要用户确认后执行。',
    policy_hints: ['refund.expedite 为 high 风险 mutation，已强制 confirm 级', 'scope=self 策略已适用'],
    steps,
    blocked: false,
  };
}

/** Scenario B: admin salary set — dual level, returns blocked=true */
export function buildScenarioBPlan(traceId: string, planId: string, approvalId: string): Plan {
  const steps: PlanStep[] = [
    { step_no: 1, kind: 'write', op_key: 'hr.salary_set', label: '设置员工薪资', capability_in: ['trusted'], capability_out: 'write', approval_request_id: approvalId, status: 'pending' },
  ];
  return {
    id: planId,
    trace_id: traceId,
    intent: '设置员工薪资（hr.salary_set）',
    writes: 1,
    required_confirm_level: 'dual',
    status: 'awaiting_confirm',
    reasoning_summary: 'hr.salary_set 为 critical 级操作，需要双人审批（dual）。',
    policy_hints: ['hr.salary_set 为 critical 级，强制 dual 审批', '需要 2 个不同管理员投票'],
    steps,
    blocked: true,
  };
}

/** Scenario C / fallback: auto plan — direct done */
export function buildScenarioCPlan(traceId: string, planId: string, intent: string): Plan {
  const steps: PlanStep[] = [
    { step_no: 1, kind: 'query', op_key: 'order.query', label: '查询订单列表', capability_in: ['trusted'], capability_out: 'data', approval_request_id: null, status: 'done' },
    { step_no: 2, kind: 'query', op_key: 'customer.query', label: '查询客户信息', capability_in: ['data'], capability_out: 'data', approval_request_id: null, status: 'done' },
  ];
  return {
    id: planId,
    trace_id: traceId,
    intent,
    writes: 0,
    required_confirm_level: 'auto',
    status: 'done',
    reasoning_summary: '只读查询，无写操作，auto 级直接执行。',
    policy_hints: ['scope=self：user_id 已被策略强制覆盖为本人'],
    steps,
    blocked: false,
  };
}
