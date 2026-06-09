import {
  createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode,
} from 'react';
import type { Role, ScreenKey, Operation, OpsStatus } from './types';
import { ROLE_NAV, OPS } from './data';

export interface Toast {
  id: number;
  text: string;
  kind: 'ok' | 'info' | 'warn';
}

interface AppCtxShape {
  role: Role;
  setRole: (r: Role) => void;
  active: ScreenKey;
  setActive: (s: ScreenKey) => void;

  /* per-screen subnav selection (resets on screen change) */
  treeSel: number;
  setTreeSel: (i: number) => void;

  /* global search query */
  query: string;
  setQuery: (q: string) => void;

  /* live, mutable operation registry */
  ops: Operation[];
  setOpStatus: (name: string, status: OpsStatus) => void;
  approveAllPending: () => number;

  opsSel: string;
  setOpsSel: (s: string) => void;
  plugSel: string;
  setPlugSel: (s: string) => void;
  flowSel: number;
  setFlowSel: (i: number) => void;

  /* toast notifications */
  toasts: Toast[];
  toast: (text: string, kind?: Toast['kind']) => void;
}

const AppCtx = createContext<AppCtxShape | null>(null);

/* default subnav row per screen — matches registry treeOn */
const DEFAULT_TREE: Record<ScreenKey, number> = {
  explore: 1, live: 2, chat: 1, flow: 1, ops: 0, audit: 1, plugins: 0,
};

export function AppProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role>('admin');
  const [active, setActiveState] = useState<ScreenKey>('explore');
  const [treeSel, setTreeSel] = useState<number>(DEFAULT_TREE.explore);
  const [query, setQuery] = useState('');
  const [ops, setOps] = useState<Operation[]>(() => OPS.map(o => ({ ...o })));
  const [opsSel, setOpsSel] = useState<string>('order.cancel');
  const [plugSel, setPlugSel] = useState<string>('explorer');
  const [flowSel, setFlowSel] = useState<number>(3);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);

  const setActive = useCallback((s: ScreenKey) => {
    setActiveState(s);
    setTreeSel(DEFAULT_TREE[s]);
    setQuery('');
  }, []);

  /* keep role permissions and active screen in sync */
  useEffect(() => {
    const allowed = ROLE_NAV[role];
    if (!allowed.includes(active)) {
      setActive(allowed.includes('chat') ? 'chat' : allowed[0]);
    }
  }, [role, active, setActive]);

  const setOpStatus = useCallback((name: string, status: OpsStatus) => {
    setOps(prev => prev.map(o => (o.name === name ? { ...o, status } : o)));
  }, []);

  const approveAllPending = useCallback(() => {
    let n = 0;
    setOps(prev => prev.map(o => {
      if (o.status === 'pending') { n++; return { ...o, status: 'active' as OpsStatus }; }
      return o;
    }));
    return n;
  }, []);

  const toast = useCallback((text: string, kind: Toast['kind'] = 'ok') => {
    const id = ++toastId.current;
    setToasts(prev => [...prev, { id, text, kind }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 2600);
  }, []);

  return (
    <AppCtx.Provider value={{
      role, setRole, active, setActive,
      treeSel, setTreeSel, query, setQuery,
      ops, setOpStatus, approveAllPending,
      opsSel, setOpsSel, plugSel, setPlugSel, flowSel, setFlowSel,
      toasts, toast,
    }}>
      {children}
    </AppCtx.Provider>
  );
}

export function useApp(): AppCtxShape {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
