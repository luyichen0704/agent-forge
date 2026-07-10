/** Demo operation fixtures from server/app/seed.py OPERATIONS list */
import type { Operation, OperationList } from '../../api/types';

export const DEMO_OPERATIONS: Operation[] = [
  {
    id: 'op-order-query', op_key: 'order.query', version: 1,
    kind: 'query', confirm_level: 'auto', risk_level: 'low', status: 'active',
    executor_binding: 'FunctionExecutor', policy_ref: 'order_query_policy',
    roles: ['customer', 'employee', 'admin'],
    perm: 'allow', scopes: { customer: 'self' },
  },
  {
    id: 'op-customer-query', op_key: 'customer.query', version: 1,
    kind: 'query', confirm_level: 'auto', risk_level: 'low', status: 'active',
    executor_binding: 'FunctionExecutor', policy_ref: 'customer_query_policy',
    roles: ['employee', 'admin'],
    perm: 'allow', scopes: {},
  },
  {
    id: 'op-order-cancel', op_key: 'order.cancel', version: 1,
    kind: 'mutation', confirm_level: 'confirm', risk_level: 'high', status: 'pending',
    executor_binding: 'FunctionExecutor', policy_ref: 'order_cancel_policy',
    roles: ['employee', 'admin'],
    perm: 'allow', scopes: {},
  },
  {
    id: 'op-refund-expedite', op_key: 'refund.expedite', version: 1,
    kind: 'mutation', confirm_level: 'confirm', risk_level: 'high', status: 'pending',
    executor_binding: 'FunctionExecutor', policy_ref: 'refund_expedite_policy',
    roles: ['customer', 'employee', 'admin'],
    perm: 'allow', scopes: { customer: 'self' },
  },
  {
    id: 'op-user-ban', op_key: 'user.ban', version: 1,
    kind: 'mutation', confirm_level: 'confirm', risk_level: 'high', status: 'pending',
    executor_binding: 'FunctionExecutor', policy_ref: 'user_ban_policy',
    roles: ['admin'],
    perm: 'allow', scopes: {},
  },
  {
    id: 'op-hr-salary', op_key: 'hr.salary_set', version: 1,
    kind: 'mutation', confirm_level: 'dual', risk_level: 'critical', status: 'pending',
    executor_binding: 'FunctionExecutor', policy_ref: 'hr_salary_set_policy',
    roles: ['admin'],
    perm: 'allow', scopes: {},
  },
];

export function buildOperationList(extra: Operation[] = []): OperationList {
  const all = [...DEMO_OPERATIONS, ...extra];
  return {
    items: all,
    pending_count: all.filter(o => o.status === 'pending').length,
    total: all.length,
  };
}
