/* Lightweight data-viz primitives — pure SVG/CSS, no chart library.
 * All values are passed in by callers from real API data. */
import type { CSSProperties, ReactNode } from 'react';
import { fmtInt } from '../../lib/format';

/* ---- StatTile: a big number with a caption ---- */
interface StatTileProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: string;
  icon?: ReactNode;
}
export function StatTile({ label, value, sub, accent, icon }: StatTileProps) {
  return (
    <div className="stat-tile">
      <div className="row between vcenter">
        <span className="stat-label">{label}</span>
        {icon}
      </div>
      <span className="stat-value" style={accent ? { color: accent } : undefined}>{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

/* ---- HBars: ranked horizontal bar list ---- */
export interface HBarItem {
  id: string;
  label: string;
  value: number;
  color?: string;
  hint?: string;
  active?: boolean;
}
interface HBarsProps {
  items: HBarItem[];
  max?: number;
  onSelect?: (id: string) => void;
  valueSuffix?: string;
}
export function HBars({ items, max, onSelect, valueSuffix = '' }: HBarsProps) {
  const peak = max ?? Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="hbars">
      {items.map((it) => {
        const w = Math.max(2, Math.round((it.value / peak) * 100));
        const clickable = !!onSelect;
        return (
          <div
            key={it.id}
            className={`hbar-row ${it.active ? 'on' : ''} ${clickable ? 'clk' : ''}`.trim()}
            {...(clickable
              ? {
                  role: 'button' as const,
                  tabIndex: 0,
                  onClick: () => onSelect!(it.id),
                  onKeyDown: (e: React.KeyboardEvent) => {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect!(it.id); }
                  },
                }
              : {})}
          >
            <span className="hbar-label" title={it.hint ?? it.label}>{it.label}</span>
            <div className="hbar-track">
              <i style={{ width: `${w}%`, background: it.color ?? 'var(--accent)' }} />
            </div>
            <span className="hbar-val tnum">{fmtInt(it.value)}{valueSuffix}</span>
          </div>
        );
      })}
      {items.length === 0 && <span className="sm muted">暂无数据</span>}
    </div>
  );
}

/* ---- Donut: proportional ring from segments ---- */
export interface DonutSeg { label: string; value: number; color: string }
interface DonutProps {
  segments: DonutSeg[];
  size?: number;
  thickness?: number;
  centerValue?: ReactNode;
  centerSub?: ReactNode;
}
export function Donut({ segments, size = 108, thickness = 14, centerValue, centerSub }: DonutProps) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="donut-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line-2)" strokeWidth={thickness} />
        {segments.map((s, i) => {
          const frac = s.value / total;
          const dash = frac * c;
          const el = (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={thickness}
              strokeDasharray={`${dash} ${c - dash}`}
              strokeDashoffset={-offset}
              strokeLinecap="butt"
            />
          );
          offset += dash;
          return el;
        })}
      </svg>
      {(centerValue != null || centerSub != null) && (
        <div className="donut-center">
          {centerValue != null && <span className="donut-value tnum">{centerValue}</span>}
          {centerSub != null && <span className="donut-sub">{centerSub}</span>}
        </div>
      )}
    </div>
  );
}

interface LegendProps { items: Array<{ label: string; color: string; value?: ReactNode }>; style?: CSSProperties }
export function DonutLegend({ items, style }: LegendProps) {
  return (
    <div className="col gap6" style={style}>
      {items.map((it, i) => (
        <div key={i} className="row vcenter gap6" style={{ fontSize: 11.5 }}>
          <i style={{ width: 9, height: 9, borderRadius: 3, background: it.color, flex: '0 0 auto' }} />
          <span className="muted2 fill">{it.label}</span>
          {it.value != null && <span className="b tnum" style={{ color: 'var(--ink)' }}>{it.value}</span>}
        </div>
      ))}
    </div>
  );
}
