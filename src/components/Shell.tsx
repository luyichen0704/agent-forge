import { useEffect, useState, type KeyboardEvent } from 'react';
import { Icon, Chip } from './kit';
import { useApp } from '../lib/appContext';
import { NAV } from '../lib/config/navigation';
import { NAV_DESC, STEP_BADGES } from '../lib/config/navDesc';
import { SCREENS } from '../screens/registry';
import { useMe, login, logout } from '../features/auth';
import { TourProvider, useTour } from '../tour/TourProvider';
import { TourOverlay } from '../tour/TourOverlay';
import { shouldOfferOnboarding } from '../tour/engine';
import { WelcomeModal } from './WelcomeModal';
import type { Role, ScreenKey } from '../api/types';

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

const ROLES: Array<[Role, string]> = [['customer', '客户'], ['employee', '员工'], ['admin', '管理员']];

function ShellInner() {
  const { active, setActive, treeSel, setTreeSel, query, setQuery, toasts, toast } = useApp();
  const me = useMe();
  const { start } = useTour();
  const role = me.data?.acting_role ?? 'admin';
  const allowed = me.data?.allowed_screens ?? [];
  const s = SCREENS[active];
  const { Main, Aside } = s;

  const [showWelcome, setShowWelcome] = useState(false);
  const [gearMenuOpen, setGearMenuOpen] = useState(false);

  // Show welcome modal on first login if onboarding is due
  useEffect(() => {
    if (me.data && shouldOfferOnboarding()) {
      setShowWelcome(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me.data?.acting_role]);

  // Close gear menu on click outside
  useEffect(() => {
    if (!gearMenuOpen) return;
    const handler = () => setGearMenuOpen(false);
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [gearMenuOpen]);

  // if the current role can't see the active screen, jump to an allowed one
  useEffect(() => {
    if (allowed.length && !allowed.includes(active)) {
      setActive(allowed.includes('chat') ? 'chat' : allowed[0]);
    }
  }, [allowed, active, setActive]);

  const rows = s.tree
    .map((label, i) => ({ label, i }))
    .filter((r) => !query || r.label.toLowerCase().includes(query.toLowerCase()));

  async function switchRole(r: Role) {
    await login(r);
    toast(`已切换身份：${ROLES.find(([k]) => k === r)?.[1]}`, 'info');
  }

  const activeNavItem = NAV.find((n) => n.k === active);
  const activeDesc = NAV_DESC[active as ScreenKey];

  return (
    <div className="wf">
      <div className="row fill">
        {/* activity rail */}
        <div className="rail" data-tour="rail">
          <span className="mk" style={{ marginBottom: 8, flexShrink: 0 }} aria-label="agent-forge">
            <Icon n="hex" s={15} c="#fff" />
          </span>
          {NAV.map((item) => {
            const ok = allowed.includes(item.k as ScreenKey);
            const desc = NAV_DESC[item.k as ScreenKey];
            return (
              <div
                key={item.k}
                className={`ricon ${active === item.k ? 'on' : ''} ${ok ? '' : 'dis'}`}
                aria-label={item.cn} aria-disabled={!ok}
                data-tour={`rail-${item.k}`}
                style={{ cursor: ok ? 'pointer' : 'not-allowed', opacity: ok ? 1 : 0.3, position: 'relative' }}
                {...(ok ? clickable(() => setActive(item.k as ScreenKey)) : {})}
              >
                <Icon n={item.ic} s={18} />
                {/* Step badge */}
                {desc.step && (
                  <span className="step-badge">{STEP_BADGES[desc.step]}</span>
                )}
                {/* Custom tooltip card */}
                <div className="rail-tip">
                  {desc.step && (
                    <div className="tip-step">Step {desc.step} · {desc.stepLabel}</div>
                  )}
                  <div className="tip-name">{item.cn}</div>
                  <div className="tip-en">{item.en}</div>
                  <div className="tip-desc">{desc.desc}</div>
                  {!ok && <div className="tip-no-access">当前角色无访问权限</div>}
                </div>
              </div>
            );
          })}
          <div style={{ flex: 1 }} />
          {/* Help button */}
          <div
            className="ricon"
            aria-label="帮助与教程"
            style={{ cursor: 'pointer', position: 'relative' }}
            {...clickable(() => setShowWelcome(true))}
          >
            <Icon n="help" s={18} />
          </div>
          {/* Gear settings menu */}
          <div
            className="ricon"
            aria-label="设置菜单"
            style={{ cursor: 'pointer', position: 'relative' }}
            onClick={(e) => { e.stopPropagation(); setGearMenuOpen((v) => !v); }}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setGearMenuOpen((v) => !v); } }}
            role="button"
            tabIndex={0}
          >
            <Icon n="gear" s={18} />
            {gearMenuOpen && (
              <div className="rail-menu" onClick={(e) => e.stopPropagation()}>
                <div className="rail-menu-item" {...clickable(() => { setGearMenuOpen(false); start(); })}>
                  <Icon n="play" s={14} c="var(--ink-3)" />重看教程
                </div>
                <div className="rail-menu-item" {...clickable(() => { setGearMenuOpen(false); setShowWelcome(true); })}>
                  <Icon n="help" s={14} c="var(--ink-3)" />重开总览
                </div>
                <div style={{ height: 1, background: 'var(--line-2)', margin: '2px 0' }} />
                <div className="rail-menu-item danger" {...clickable(() => { setGearMenuOpen(false); logout(); })}>
                  <Icon n="logout" s={14} c="var(--danger)" />退出登录
                </div>
              </div>
            )}
          </div>
        </div>

        {/* subnav */}
        <div className="subnav">
          <div className="row vcenter between" style={{ padding: '14px 12px 10px' }}>
            <div className="logo">
              <span>agent<span style={{ color: 'var(--accent)' }}>·</span>forge</span>
            </div>
            <Icon n="help" s={15} c="var(--ink-4)" />
          </div>
          <div style={{ padding: '0 8px' }}>
            <label className="field" style={{ height: 28, fontSize: 11 }}>
              <Icon n="search" s={13} c="var(--ink-4)" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索…" aria-label="搜索" />
            </label>
          </div>
          <div className="col scroll fill" style={{ marginTop: 10 }}>
            <div className="eyebrow" style={{ padding: '0 16px 2px' }}>
              {activeNavItem?.cn}
              {activeDesc?.step && (
                <span style={{ color: 'var(--accent)', marginLeft: 5, fontSize: 11, letterSpacing: 0 }}>
                  {STEP_BADGES[activeDesc.step]} {activeDesc.stepLabel}
                </span>
              )}
            </div>
            {activeDesc?.desc && (
              <div className="screen-desc">{activeDesc.desc}</div>
            )}
            {rows.length === 0 && <div className="sm muted" style={{ padding: '6px 16px' }}>无匹配项</div>}
            {rows.map(({ label, i }) => (
              <div key={i} className={`navitem ${i === treeSel ? 'on' : ''}`} {...clickable(() => setTreeSel(i))}>
                <Icon n={s.treeIc[i]} s={13} c={i === treeSel ? 'var(--accent)' : 'var(--ink-4)'} />
                <span className="fill" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {label}
                </span>
                <Icon n="chevron" s={11} c="var(--ink-4)" />
              </div>
            ))}
          </div>
          <div style={{ padding: 10, borderTop: '1px solid var(--line-2)' }} className="col gap6">
            <span className="eyebrow">身份 · 切换看权限差异</span>
            <div className="roles" data-tour="role-switch">
              {ROLES.map(([k, label]) => (
                <span key={k} className={role === k ? 'on' : ''} style={{ cursor: 'pointer' }}
                  onClick={() => switchRole(k)}>{label}</span>
              ))}
            </div>
          </div>
        </div>

        {/* main */}
        <div className="col fill" style={{ background: 'var(--canvas)', minWidth: 0 }}>
          <div className="row between vcenter"
            style={{ padding: '12px 18px', borderBottom: '1px solid var(--line)', background: 'var(--paper)', flexShrink: 0 }}>
            <div className="col">
              <span className="h2">{s.title}</span>
              <span className="sm muted">{s.sub}</span>
            </div>
            <div className="row vcenter gap8">
              {active === 'chat' && <Chip ic="shield">CaMeL 已启用</Chip>}
              <Chip>{ROLES.find(([k]) => k === role)?.[1] ?? role}</Chip>
            </div>
          </div>
          <Main />
        </div>

        {/* aside */}
        <div className="col aside-panel" data-tour="chat-aside"
          style={{ width: s.asideW, flex: '0 0 auto', borderLeft: '1px solid var(--line)', background: 'var(--paper)' }}>
          <Aside />
        </div>
      </div>

      <div className="toast-host" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}><span className="tdot" />{t.text}</div>
        ))}
      </div>

      {/* Tour overlay */}
      <TourOverlay />

      {/* Welcome modal */}
      {showWelcome && <WelcomeModal onClose={() => setShowWelcome(false)} />}
    </div>
  );
}

export function Shell() {
  return (
    <TourProvider>
      <ShellInner />
    </TourProvider>
  );
}
