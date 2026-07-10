/** Demo user fixtures from server/app/seed.py */
import type { Me, Role, ScreenKey } from '../../api/types';

const ALLOWED_SCREENS: Record<string, ScreenKey[]> = {
  customer: ['chat', 'flow'],
  employee: ['chat', 'flow', 'live', 'ops'],
  admin: ['explore', 'live', 'chat', 'flow', 'ops', 'audit', 'plugins'],
};

export interface DemoUser {
  id: string;
  email: string;
  display_name: string;
  password: string;
  role: Role;
}

export const DEMO_USERS: DemoUser[] = [
  { id: 'u-zhang', email: 'zhang@demo.com', display_name: '张伟', password: 'demo1234', role: 'customer' },
  { id: 'u-wei', email: 'wei@company.com', display_name: '员工小卫', password: 'demo1234', role: 'employee' },
  { id: 'u-admin', email: 'admin@company.com', display_name: '管理员', password: 'demo1234', role: 'admin' },
  { id: 'u-admin2', email: 'admin2@company.com', display_name: '管理员乙', password: 'demo1234', role: 'admin' },
];

export function buildMe(user: DemoUser): Me {
  return {
    user: { id: user.id, email: user.email, display_name: user.display_name },
    tenant: { id: 't-demo', name: 'Demo 企业', slug: 'demo' },
    acting_role: user.role,
    roles: [user.role],
    allowed_screens: ALLOWED_SCREENS[user.role] as ScreenKey[],
  };
}
