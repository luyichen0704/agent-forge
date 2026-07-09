import { useMemo } from 'react';
import { Icon, Btn, Tag, Dot, Note, StatTile, HBars, Donut, DonutLegend } from '../components/kit';
import type { HBarItem } from '../components/kit';
import { useApp } from '../lib/appContext';
import { useMe } from '../features/auth';
import { useSources, useStartExplore } from '../features/sources';
import { useOperations } from '../features/operations';
import { useQueryClient } from '@tanstack/react-query';
import { explorerLabel, srcStatusLabel } from '../lib/labels';
import { shortSourceName, fmtInt, pct } from '../lib/format';

const iconBox: React.CSSProperties = {
  width: 34, height: 34, borderRadius: 8, background: 'var(--fill)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
};
const SRC_ICON: Record<string, string> = { code: 'code', db: 'db', api: 'globe', admin: 'table', doc: 'doc' };

// Theme-aware categorical palette — resolves to lighter hues in dark mode
// (tokens defined in index.css). Kept in sync with viz.tsx consumers.
const BAR_PALETTE = [
  'var(--viz-1)', 'var(--viz-2)', 'var(--viz-3)', 'var(--viz-4)', 'var(--viz-5)',
  'var(--viz-6)', 'var(--viz-7)', 'var(--viz-8)', 'var(--viz-9)', 'var(--viz-10)',
];

/* 总览：各系统操作数、读/写分布、真实接口绑定占比 —— 全部来自真实 /operations。 */
function OverviewPanel() {
  const ops = useOperations();
  const srcs = useSources();
  const items = useMemo(() => ops.data?.items ?? [], [ops.data]);

  const stats = useMemo(() => {
    const total = items.length;
    const q = items.filter((o) => o.kind === 'query').length;
    const mut = total - q;
    const active = items.filter((o) => o.status === 'active').length;
    const pending = items.filter((o) => o.status === 'pending').length;
    const bound = items.filter((o) => !!o.call).length;
    const m = new Map<string, { name: string | null; count: number }>();
    for (const o of items) {
      const key = o.source_id ?? '__none__';
      const e = m.get(key) ?? { name: o.source_name ?? null, count: 0 };
      e.count++; m.set(key, e);
    }
    const bySource: HBarItem[] = [...m.entries()]
      .filter(([id]) => id !== '__none__')
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 8)
      .map(([id, e], i) => ({ id, label: shortSourceName(e.name), value: e.count, color: BAR_PALETTE[i % BAR_PALETTE.length] }));
    return { total, q, mut, active, pending, bound, bySource };
  }, [items]);

  if (ops.isLoading) return <div className="card pad16 muted sm">加载总览…</div>;
  if (ops.isError) return null;

  const srcCount = srcs.data?.items.length ?? 0;
  const bindPct = pct(stats.bound, stats.total);

  return (
    <div className="card pad16 col gap14">
      <div className="row vcenter gap8">
        <Icon n="bars" s={15} c="var(--accent)" />
        <span className="h3">接入总览</span>
        <span className="sm muted">· 全部来自已接入系统的真实探索结果</span>
      </div>

      <div className="stat-grid">
        <StatTile label="已接入系统" value={<span className="tnum">{srcCount}</span>} sub="企业数据源" accent="var(--accent-ink)" icon={<Icon n="grid" s={15} c="var(--ink-4)" />} />
        <StatTile label="可用操作" value={<span className="tnum">{fmtInt(stats.total)}</span>} sub="自动发现" accent="var(--cap-data)" icon={<Icon n="bolt" s={15} c="var(--ink-4)" />} />
        <StatTile label="已上线（查询）" value={<span className="tnum">{fmtInt(stats.active)}</span>} sub="可直接调用" accent="var(--cap-trusted)" icon={<Icon n="check" s={15} c="var(--ink-4)" />} />
        <StatTile label="待审核（写操作）" value={<span className="tnum">{fmtInt(stats.pending)}</span>} sub="需人工上线" accent="var(--cap-write)" icon={<Icon n="refresh" s={15} c="var(--ink-4)" />} />
      </div>

      <div className="overview-charts">
        <div className="col gap8 fill" style={{ minWidth: 260 }}>
          <span className="eyebrow">各系统操作数（前 8）</span>
          <HBars items={stats.bySource} />
        </div>
        <div className="row gap16 wrap" style={{ flex: '0 0 auto' }}>
          <div className="col vcenter gap8">
            <span className="eyebrow">读 / 写分布</span>
            <Donut
              segments={[
                { label: '查询', value: stats.q, color: 'var(--cap-data)' },
                { label: '修改', value: stats.mut, color: 'var(--cap-write)' },
              ]}
              centerValue={fmtInt(stats.total)} centerSub="操作" />
            <DonutLegend items={[
              { label: '查询', color: 'var(--cap-data)', value: fmtInt(stats.q) },
              { label: '修改', color: 'var(--cap-write)', value: fmtInt(stats.mut) },
            ]} />
          </div>
          <div className="col vcenter gap8">
            <span className="eyebrow">真实接口绑定</span>
            <Donut
              segments={[
                { label: '已绑定', value: stats.bound, color: 'var(--cap-trusted)' },
                { label: '未绑定', value: stats.total - stats.bound, color: 'var(--line)' },
              ]}
              centerValue={`${bindPct}%`} centerSub="已对接" />
            <span className="xs muted tnum">{fmtInt(stats.bound)} / {fmtInt(stats.total)} 个操作</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ExploreMain() {
  const { treeSel, setTreeSel, toast } = useApp();
  const role = useMe().data?.acting_role ?? 'admin';
  const { data, isLoading } = useSources();

  if (isLoading) return <div className="pad16 muted sm">加载数据源…</div>;
  const sources = data?.items ?? [];

  return (
    <div className="col gap12 fill scroll" style={{ padding: 16 }}>
      <OverviewPanel />
      <div className="row vcenter gap8" style={{ marginTop: 2 }}>
        <span className="eyebrow">已接入的数据源（{sources.length}）</span>
        <span className="sm muted">点击任一系统查看详情或触发探索</span>
      </div>
      {sources.map((s, i) => {
        const selected = treeSel === i + 1;
        return (
          <div key={s.id} className="card hover row vcenter gap12"
            style={{ padding: 12, cursor: 'pointer', borderColor: selected ? 'var(--accent)' : 'var(--line)',
                     boxShadow: selected ? '0 0 0 1px var(--accent)' : undefined }}
            role="button" tabIndex={0} onClick={() => setTreeSel(i + 1)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTreeSel(i + 1); } }}>
            <span style={iconBox}><Icon n={SRC_ICON[s.type] ?? 'doc'} s={18} c="var(--ink-2)" /></span>
            <div className="col" style={{ width: 150 }}>
              <span className="b sm">{s.name}</span>
              <span className="xs muted mono">{s.conn}</span>
            </div>
            <div className="fill">
              {s.status === 'running' && s.progress != null && (
                <div className="prog" style={{ maxWidth: 220 }}><i style={{ width: `${s.progress}%` }} /></div>
              )}
            </div>
            <div className="row vcenter gap6 sm muted2">
              <Dot k={s.status === 'connected' ? 'ok' : s.status === 'running' ? 'wait' : 'off'} />
              {srcStatusLabel(s.status)}
            </div>
            <Icon n="chevron" s={16} c="var(--ink-4)" />
          </div>
        );
      })}
      {role === 'admin' && (
        <div className="card row vcenter gap12" style={{ padding: 12, borderStyle: 'dashed', background: 'var(--fill-2)' }}>
          <span style={{ ...iconBox, background: 'var(--accent-soft)' }}><Icon n="puzzle" s={18} c="var(--accent-ink)" /></span>
          <div className="col fill">
            <span className="b sm">接入新的数据源</span>
            <span className="xs muted">按标准方式接入，即可挂载任意企业系统</span>
          </div>
          <Btn sz="sm" ic="plus" onClick={() => toast('打开数据源接入向导（演示）', 'info')}>添加</Btn>
        </div>
      )}
    </div>
  );
}

export function ExploreAside() {
  const { treeSel, toast } = useApp();
  const role = useMe().data?.acting_role ?? 'admin';
  const { data } = useSources();
  const explore = useStartExplore();
  const qc = useQueryClient();
  const sources = data?.items ?? [];
  const idx = treeSel >= 1 && treeSel <= sources.length ? treeSel - 1 : 0;
  const src = sources[idx];

  if (!src) return <div className="pad14 muted sm">无数据源</div>;

  return (
    <div className="col fill">
      <div className="row between vcenter" style={{ padding: '12px 14px', borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3">{explorerLabel(src.connector_kind)}</span>
        <Tag k={src.status === 'connected' ? 'trusted' : 'parsed'}>{srcStatusLabel(src.status)}</Tag>
      </div>
      <div className="col gap12 fill scroll" style={{ padding: 14 }}>
        <div className="col gap6">
          <span className="eyebrow">连接信息</span>
          <div className="field" style={{ gap: 0 }}><span className="mono xs" style={{ color: 'var(--ink-2)' }}>{src.conn}</span></div>
        </div>
        {role === 'admin' && (
          <Btn k="pri" ic="play" disabled={explore.isPending}
            data-tour="explore-start"
            onClick={() => explore.mutate(src.id, {
              onSuccess: (r) => {
                qc.setQueryData(['job-latest'], r.job_id);
                toast('已启动探索 · 前往「实时探索」查看', 'info');
              },
              onError: (e) => toast((e as Error).message, 'warn'),
            })}>开始探索</Btn>
        )}
        <div className="divln" />
        <span className="eyebrow">工作方式</span>
        <Note>系统会自动读取该数据源，发现其中可用的操作，并登记到操作清单（读操作自动上线，写操作待审核）。</Note>
      </div>
    </div>
  );
}
