/* ============================================================
   CaMeL-Business · shared types
   ============================================================ */

export type Role = 'customer' | 'employee' | 'admin';

export type ScreenKey = 'explore' | 'live' | 'chat' | 'flow' | 'ops' | 'audit' | 'plugins';

export type CapKind = 'trusted' | 'data' | 'parsed' | 'write';

export type DotKind = CapKind | 'ok' | 'wait' | 'off';

export type TagKind = 'q' | 'm' | CapKind;

export type OpsConfirm = 'auto' | 'confirm' | 'dual';
export type OpsStatus = 'active' | 'pending';
export type OpsType = 'q' | 'm';

export interface Operation {
  name: string;
  type: OpsType;
  perm: string;
  confirm: OpsConfirm;
  status: OpsStatus;
  roles: Role[];
}

export interface FlowNode {
  cap: CapKind;
  label: string;
  /* short node name for inspector header */
  node: string;
  source: string;
  readers: string;
  via: string;
}

export interface AuditEvent {
  event: string;
  detail: string;
  cap: CapKind | 'data';
}

export interface DataSource {
  icon: string;
  label: string;
  conn: string;
  statusLabel: string;
  dotKind: DotKind;
  progress?: number;
}

export interface ExplorePhase {
  label: string;
  sub: string;
  state: 'done' | 'now' | 'todo';
}

export interface ChatPlan {
  q: string;
  note: string | null;
  plan: Array<[string, string, string]>;
  writes: number;
  foot: string;
  done: string;
}

export interface Plugin {
  key: string;
  iface: string;
  sub: string;
  ic: string;
  impls: Array<[string, DotKind]>;
  code: string;
}

export interface NavItem {
  k: ScreenKey;
  cn: string;
  en: string;
  ic: string;
}

export interface ScreenConfig {
  title: string;
  sub: string;
  asideW: number;
  tree: string[];
  treeIc: string[];
  treeOn: number;
  actions?: Array<[string, string, string]>;
  prog?: number;
  Main: () => React.ReactElement;
  Aside: () => React.ReactElement;
}
