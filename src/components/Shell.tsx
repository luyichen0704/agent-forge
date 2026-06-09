import type { KeyboardEvent } from 'react';
import { Icon, Chip, Btn, RoleSwitch } from './kit';
import { useApp } from '../lib/appContext';
import { NAV, ROLE_NAV } from '../lib/data';
import { SCREENS } from '../screens/registry';
import type { ScreenKey } from '../lib/types';

/* keyboard-accessible click props for non-button elements */
function clickable(onClick: () => void) {
  return {
    role: 'button' as const,
    tabIndex: 0,
    onClick,
    onKeyDown: (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); }
    },
  };
}

export function Shell() {
  const {
    role, setRole, active, setActive,
    treeSel, setTreeSel, query, setQuery,
    approveAllPending, toast, toasts,
  } = useApp();
  const allowed = ROLE_NAV[role];
  const s = SCREENS[active];
  const { Main, Aside } = s;

  /* filter subnav rows by search, preserving original indices */
  const rows = s.tree
    .map((label, i) => ({ label, i }))
    .filter(r => !query || r.label.toLowerCase().includes(query.toLowerCase()));

  /* titlebar action handler */
  function runAction(label: string) {
    switch (label) {
      case '批量批准': {
        const n = approveAllPending();
        toast(n ? `已批准 ${n} 个待审操作` : '没有待审操作', n ? 'ok' : 'info');
        break;
      }
      case '开始探索':
        toast('已启动探索 · CodeExplorer 运行中', 'info'); break;
      case '增量更新':
        toast('已触发增量更新'); break;
      case '导出审计':
      case '导出':
        toast('审计链已导出 · trace-abc123.json'); break;
      case '展开全部':
        toast('已展开全部节点', 'info'); break;
      default:
        toast(label);
    }
  }

  return (
    <div className="wf">
      <div className="row fill">
        {/* ── activity rail ── */}
        <div className="rail">
          <span className="mk" style={{ marginBottom: 8, flexShrink: 0 }} aria-label="agent-forge">
            <Icon n="hex" s={15} c="#fff" />
          </span>

          {NAV.map(item => {
            const ok = allowed.includes(item.k as ScreenKey);
            return (
              <div
                key={item.k}
                className={`ricon ${active === item.k ? 'on' : ''} ${ok ? '' : 'dis'}`}
                title={item.cn + (ok ? '' : ' · 当前角色无权')}
                aria-label={item.cn}
                aria-disabled={!ok}
                style={{ cursor: ok ? 'pointer' : 'not-allowed', opacity: ok ? 1 : 0.3 }}
                {...(ok ? clickable(() => setActive(item.k as ScreenKey)) : {})}
              >
                <Icon n={item.ic} s={18} />
              </div>
            );
          })}

          <div style={{ flex: 1 }} />
          <div className="ricon" aria-label="设置" {...clickable(() => toast('设置面板（演示）', 'info'))}>
            <Icon n="gear" s={18} />
          </div>
        </div>

        {/* ── subnav ── */}
        <div className="subnav">
          <div className="row vcenter between" style={{ padding: '14px 12px 10px' }}>
            <div className="logo">
              <span style={{ letterSpacing: '-0.02em' }}>
                agent<span style={{ color: 'var(--accent)' }}>·</span>forge
              </span>
            </div>
            <Icon n="dots" s={15} c="var(--ink-4)" />
          </div>

          <div style={{ padding: '0 8px' }}>
            <label className="field" style={{ height: 28, fontSize: 11 }}>
              <Icon n="search" s={13} c="var(--ink-4)" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="搜索…"
                aria-label="搜索"
              />
            </label>
          </div>

          <div className="col scroll fill" style={{ marginTop: 10 }}>
            <div className="eyebrow" style={{ padding: '0 16px 4px' }}>
              {NAV.find(n => n.k === active)?.cn}
            </div>
            {rows.length === 0 && (
              <div className="sm muted" style={{ padding: '6px 16px' }}>无匹配项</div>
            )}
            {rows.map(({ label, i }) => (
              <div
                key={i}
                className={`navitem ${i === treeSel ? 'on' : ''}`}
                {...clickable(() => setTreeSel(i))}
              >
                <Icon n={s.treeIc[i]} s={13} c={i === treeSel ? 'var(--accent)' : 'var(--ink-4)'} />
                <span className="fill" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {label}
                </span>
              </div>
            ))}
          </div>

          <div style={{ padding: 10, borderTop: '1px solid var(--line-2)' }} className="col gap6">
            <span className="eyebrow">身份 · 切换看权限差异</span>
            <RoleSwitch value={role} onChange={setRole} />
          </div>
        </div>

        {/* ── main area ── */}
        <div className="col fill" style={{ background: 'var(--canvas)', minWidth: 0 }}>
          {/* titlebar */}
          <div
            className="row between vcenter"
            style={{
              padding: '12px 18px',
              borderBottom: '1px solid var(--line)',
              background: 'var(--paper)',
              flexShrink: 0,
            }}
          >
            <div className="col">
              <span className="h2">{s.title}</span>
              <span className="sm muted">{s.sub}</span>
            </div>
            <div className="row vcenter gap8">
              {s.prog != null && (
                <>
                  <span className="sm muted tnum">{s.prog}%</span>
                  <div className="prog" style={{ width: 130 }}>
                    <i style={{ width: `${s.prog}%` }} />
                  </div>
                </>
              )}
              {active === 'chat' && (
                <>
                  <Chip ic="shield">CaMeL 已启用</Chip>
                  <Chip>{role}</Chip>
                </>
              )}
              {active === 'ops' && role !== 'admin' && <Chip ic="eye">只读视角</Chip>}
              {s.actions && (active !== 'ops' || role === 'admin') &&
                s.actions.map(([ic, l, k], i) => (
                  <Btn key={i} sz="sm" ic={ic} k={k} onClick={() => runAction(l)}>{l}</Btn>
                ))}
            </div>
          </div>

          {/* screen main content */}
          <Main />
        </div>

        {/* ── right inspector aside ── */}
        <div
          className="col aside-panel"
          style={{
            width: s.asideW,
            flex: '0 0 auto',
            borderLeft: '1px solid var(--line)',
            background: 'var(--paper)',
          }}
        >
          <Aside />
        </div>
      </div>

      {/* ── toast host ── */}
      <div className="toast-host" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <span className="tdot" />
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}
