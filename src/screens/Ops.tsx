import { Icon, Btn, Chip, Tag, Dot, Note } from '../components/kit';
import { useApp } from '../lib/appContext';
import { useMe } from '../features/auth';
import { useOperations, usePublishOperation, useDisableOperation } from '../features/operations';
import { useApprovals, useVote } from '../features/approvals';
import { useLlmProfiles, useLlmModels, usePatchProfile } from '../features/llm';
import { useEffect, useMemo, useState } from 'react';
import type { ApprovalRequest } from '../api/types';
import {
  opTitle, kindLabel, confirmLabel, opStatusLabel, permLabel, riskLabel,
  executorLabel, llmRoleLabel, approvalStatusLabel,
} from '../lib/labels';
import { shortSourceName, fmtInt } from '../lib/format';

function LlmSettingsPanel() {
  const { toast } = useApp();
  const { data } = useLlmProfiles();
  const [fetchModels, setFetchModels] = useState(false);
  const models = useLlmModels(fetchModels);
  const patch = usePatchProfile();
  const [edit, setEdit] = useState<Record<string, { model?: string; max_tokens?: number }>>({});

  const items = data?.items ?? [];
  const opts = models.data?.models ?? [];

  return (
    <div className="col gap8" style={{ marginTop: 16 }}>
      <div className="row vcenter between">
        <span className="eyebrow">模型设置</span>
        <button className="btn sm" disabled={models.isFetching}
          onClick={() => setFetchModels(true)}>
          {models.isFetching ? '拉取中…' : '拉取可用模型'}
        </button>
      </div>
      {items.map((p) => {
        const e = edit[p.role] ?? {};
        const model = e.model ?? p.model;
        const maxTok = e.max_tokens ?? p.max_tokens;
        return (
          <div key={p.role} className="card pad12 row vcenter gap10 wrap">
            <span className="b sm" style={{ width: 92 }}>{llmRoleLabel(p.role)}</span>
            {opts.length ? (
              <select value={model} onChange={(ev) => setEdit({ ...edit, [p.role]: { ...e, model: ev.target.value } })}
                style={selStyle}>
                {[model, ...opts.filter((m) => m !== model)].map((m) => <option key={m}>{m}</option>)}
              </select>
            ) : (
              <input value={model} onChange={(ev) => setEdit({ ...edit, [p.role]: { ...e, model: ev.target.value } })}
                style={selStyle} />
            )}
            <label className="row vcenter gap5 xs muted">回复长度上限
              <input type="number" value={maxTok} style={{ ...selStyle, width: 90 }}
                onChange={(ev) => setEdit({ ...edit, [p.role]: { ...e, max_tokens: Number(ev.target.value) } })} />
            </label>
            <Btn sz="sm" k="go" ic="check" disabled={patch.isPending}
              onClick={() => patch.mutate({ role: p.role, body: { model, max_tokens: maxTok } },
                { onSuccess: () => toast(`已更新${llmRoleLabel(p.role)}为 ${model}`), onError: (er) => toast((er as Error).message, 'warn') })}>
              保存
            </Btn>
          </div>
        );
      })}
      {data && <span className="xs muted">改动即时生效，无需重启</span>}
    </div>
  );
}

const selStyle: React.CSSProperties = {
  height: 28, border: '1px solid var(--line)', borderRadius: 6, padding: '0 8px',
  font: 'inherit', fontSize: 12, background: 'var(--paper)', minWidth: 200,
};

function ApprovalRow({ ar }: { ar: ApprovalRequest }) {
  const { toast } = useApp();
  const vote = useVote(ar.id);
  return (
    <div className="card pad12 row vcenter gap12">
      <Tag k="write">{confirmLabel(ar.confirm_level)}</Tag>
      <div className="col fill">
        <span className="b sm">{ar.target_type === 'operation' ? '操作上线审批' : '写操作审批'}</span>
        <span className="xs muted">已批准 {ar.approve_votes}/{ar.required_votes} · {approvalStatusLabel(ar.status)}</span>
      </div>
      <Btn sz="sm" k="go" ic="check" disabled={vote.isPending || ar.status !== 'pending'}
        data-tour="ops-approve"
        onClick={() => vote.mutate({ decision: 'approve' }, {
          onSuccess: (r) => toast(r.status === 'approved' ? '已批准并满足条件' : `已投票 (${r.approve_votes}/${r.required_votes})`),
          onError: (e) => toast((e as Error).message, 'warn'),
        })}>批准</Btn>
      <Btn sz="sm" k="warn" ic="x" disabled={vote.isPending || ar.status !== 'pending'}
        onClick={() => vote.mutate({ decision: 'reject' }, { onSuccess: () => toast('已拒绝', 'warn') })}>拒绝</Btn>
    </div>
  );
}

function ApprovalsPanel() {
  const { data } = useApprovals('pending');
  const items = data?.items ?? [];
  return (
    <div className="col gap8" style={{ marginTop: 16 }} data-tour="ops-approvals">
      <span className="eyebrow">待人工审批（{items.length}）</span>
      {items.length === 0 && <span className="sm muted">暂无待审批请求。</span>}
      {items.map((ar) => <ApprovalRow key={ar.id} ar={ar} />)}
    </div>
  );
}

type KindF = 'all' | 'query' | 'mutation';
type StatusF = 'all' | 'pending' | 'active' | 'disabled';
const PAGE_SIZE = 40;

/** Map the subnav tree preset (treeSel) → in-page kind/status filters. */
function presetFromTree(treeSel: number): { kind: KindF; status: StatusF } {
  switch (treeSel) {
    case 1: return { kind: 'all', status: 'pending' };
    case 2: return { kind: 'query', status: 'active' };
    case 3: return { kind: 'mutation', status: 'all' };
    case 4: return { kind: 'all', status: 'disabled' };
    default: return { kind: 'all', status: 'all' };
  }
}

const stColor = (s: string) => (s === 'active' ? 'var(--cap-trusted)' : s === 'disabled' ? 'var(--ink-4)' : 'var(--cap-write)');

function Pill({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button className={`pill ${on ? 'on' : ''}`.trim()} onClick={onClick}>{children}</button>;
}

export function OpsMain() {
  const { opsSel, setOpsSel, treeSel } = useApp();
  const role = useMe().data?.acting_role ?? 'admin';
  const { data, isLoading, isError } = useOperations();
  const readonly = role !== 'admin';

  const [srcFilter, setSrcFilter] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [kindF, setKindF] = useState<KindF>('all');
  const [statusF, setStatusF] = useState<StatusF>('all');
  const [page, setPage] = useState(0);

  // subnav preset drives the in-page kind/status filters
  useEffect(() => {
    const p = presetFromTree(treeSel);
    setKindF(p.kind); setStatusF(p.status);
  }, [treeSel]);

  // any filter change resets to first page
  useEffect(() => { setPage(0); }, [srcFilter, search, kindF, statusF]);

  const items = useMemo(() => data?.items ?? [], [data]);

  // source list with counts (largest first); ops without a source_id grouped as 内置
  const bySource = useMemo(() => {
    const m = new Map<string, { name: string | null; count: number }>();
    for (const o of items) {
      const key = o.source_id ?? '__none__';
      const e = m.get(key) ?? { name: o.source_name ?? null, count: 0 };
      e.count++; m.set(key, e);
    }
    return [...m.entries()].sort((a, b) => b[1].count - a[1].count);
  }, [items]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((o) => {
      if (srcFilter === '__none__') { if (o.source_id) return false; }
      else if (srcFilter !== 'all' && o.source_id !== srcFilter) return false;
      if (kindF !== 'all' && o.kind !== kindF) return false;
      if (statusF !== 'all' && o.status !== statusF) return false;
      if (q) {
        const hay = `${opTitle(o)} ${o.op_key} ${o.call ?? ''} ${o.source_name ?? ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [items, srcFilter, kindF, statusF, search]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const curPage = Math.min(page, pageCount - 1);
  const start = curPage * PAGE_SIZE;
  const pageItems = filtered.slice(start, start + PAGE_SIZE);

  if (isLoading) return <div className="pad16 muted sm">加载操作清单…</div>;
  if (isError || !data) return (
    <div className="pad16 col gap8 sm">
      <span style={{ color: 'var(--danger)' }}>操作清单加载失败。</span>
      <span className="muted">请检查是否已登录、后端是否可用，稍后重试。</span>
    </div>
  );

  return (
    <div className="pad16 fill scroll col gap12">
      {readonly && (
        <div className="row vcenter gap6 sm muted">
          <Icon n="eye" s={14} c="var(--ink-3)" />当前身份 · 只显示你可调用的操作 · 审核为只读
        </div>
      )}

      {/* controls */}
      <div className="ops-controls">
        <label className="field" style={{ minWidth: 200, flex: '1 1 220px' }}>
          <Icon n="search" s={13} c="var(--ink-4)" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索操作名称 / 关键词…" aria-label="搜索操作" />
        </label>
        <select className="sel" aria-label="按系统筛选" value={srcFilter}
          onChange={(e) => setSrcFilter(e.target.value)} style={{ maxWidth: 240 }}>
          <option value="all">全部系统（{fmtInt(items.length)}）</option>
          {bySource.map(([id, e]) => (
            <option key={id} value={id}>
              {(id === '__none__' ? '内置操作' : shortSourceName(e.name))}（{e.count}）
            </option>
          ))}
        </select>
      </div>
      <div className="row gap6 wrap vcenter">
        <span className="eyebrow" style={{ marginRight: 2 }}>类型</span>
        <Pill on={kindF === 'all'} onClick={() => setKindF('all')}>全部</Pill>
        <Pill on={kindF === 'query'} onClick={() => setKindF('query')}>查询</Pill>
        <Pill on={kindF === 'mutation'} onClick={() => setKindF('mutation')}>修改</Pill>
        <span style={{ width: 8 }} />
        <span className="eyebrow" style={{ marginRight: 2 }}>状态</span>
        <Pill on={statusF === 'all'} onClick={() => setStatusF('all')}>全部</Pill>
        <Pill on={statusF === 'pending'} onClick={() => setStatusF('pending')}>待审核</Pill>
        <Pill on={statusF === 'active'} onClick={() => setStatusF('active')}>已上线</Pill>
        <Pill on={statusF === 'disabled'} onClick={() => setStatusF('disabled')}>已停用</Pill>
      </div>

      {/* result counter */}
      <div className="row vcenter between sm muted">
        <span>
          共 <b className="tnum" style={{ color: 'var(--ink)' }}>{fmtInt(filtered.length)}</b> 个操作
          {filtered.length > 0 && <> · 第 {fmtInt(start + 1)}–{fmtInt(Math.min(start + PAGE_SIZE, filtered.length))} 条</>}
        </span>
        {pageCount > 1 && (
          <span className="row vcenter gap6">
            <button className="pg-btn" disabled={curPage === 0} onClick={() => setPage(curPage - 1)} aria-label="上一页">
              <Icon n="chevron" s={13} style={{ transform: 'rotate(180deg)' }} />
            </button>
            <span className="tnum">{curPage + 1} / {pageCount}</span>
            <button className="pg-btn" disabled={curPage >= pageCount - 1} onClick={() => setPage(curPage + 1)} aria-label="下一页">
              <Icon n="chevron" s={13} />
            </button>
          </span>
        )}
      </div>

      <div className="card" style={{ overflow: 'hidden', flex: '0 0 auto' }} data-tour="ops-table">
        <table className="tbl">
          <thead><tr style={{ cursor: 'default' }}>
            <th>操作</th><th>系统</th><th>类型</th><th>确认级别</th><th>状态</th><th></th>
          </tr></thead>
          <tbody>
            {pageItems.length === 0 && (
              <tr style={{ cursor: 'default' }}>
                <td colSpan={6} className="muted sm" style={{ padding: '20px 12px', textAlign: 'center' }}>
                  没有符合条件的操作，试试放宽筛选或更换关键词。
                </td>
              </tr>
            )}
            {pageItems.map((o) => (
              <tr key={o.id} className={o.id === opsSel ? 'sel' : ''} onClick={() => setOpsSel(o.id)}>
                <td className="b" style={{ color: 'var(--ink)' }}>
                  <div className="col" style={{ gap: 1 }}>
                    <span>{opTitle(o)}</span>
                    <span className="xs muted mono" style={{ fontWeight: 400 }}>{o.op_key}</span>
                  </div>
                </td>
                <td className="sm muted2" style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {o.source_name ? shortSourceName(o.source_name) : '内置'}
                </td>
                <td><Tag k={o.kind === 'mutation' ? 'm' : 'q'}>{kindLabel(o.kind)}</Tag></td>
                <td>{o.confirm_level === 'dual'
                  ? <span style={{ color: 'var(--danger)' }} className="b">需双人审批</span> : confirmLabel(o.confirm_level)}</td>
                <td><span className="row vcenter gap5">
                  <Dot k={o.status === 'active' ? 'ok' : o.status === 'disabled' ? 'off' : 'wait'} />
                  <span style={{ color: stColor(o.status) }}>{opStatusLabel(o.status)}</span>
                </span></td>
                <td><Icon n="chevron" s={15} c="var(--ink-4)" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {role === 'admin' && (
        <div className="col gap8" style={{ marginTop: 4 }}>
          <span className="eyebrow">可扩展的后端能力</span>
          <div className="row gap8 wrap">
            <Chip ic="puzzle">策略引擎 · 可按需接入</Chip>
            <Chip ic="bolt">执行方式 · 接口 / 数据库 / 流程</Chip>
          </div>
          <ApprovalsPanel />
          <LlmSettingsPanel />
        </div>
      )}
    </div>
  );
}

export function OpsAside() {
  const { opsSel, toast } = useApp();
  const role = useMe().data?.acting_role ?? 'admin';
  const { data } = useOperations();
  const publish = usePublishOperation();
  const disable = useDisableOperation();

  const o = data?.items.find((x) => x.id === opsSel) ?? data?.items[0];
  if (!o) return <div className="pad14 muted sm">选择左侧任一操作查看详情。</div>;
  const isM = o.kind === 'mutation';

  return (
    <div className="col pad14 fill gap10 scroll">
      <div className="row between vcenter">
        <div className="col" style={{ gap: 1, minWidth: 0 }}>
          <span className="h3">{opTitle(o)}</span>
          <span className="xs muted mono">{o.op_key}</span>
        </div>
        <Tag k={isM ? 'm' : 'q'}>{kindLabel(o.kind)}</Tag>
      </div>
      {([
        ['所属系统', o.source_name ? shortSourceName(o.source_name) : '内置操作'],
        ['说明', isM ? '执行一次写操作（会改动数据）' : '查询数据（不改动）'],
        ['权限', permLabel(o.perm)],
        ['确认级别', confirmLabel(o.confirm_level)],
        ['风险', riskLabel(o.risk_level)],
        ['执行方式', executorLabel(o.executor_binding)],
      ] as [string, string][]).map(([k, v], i) => (
        <div key={i} className="row gap8 sm">
          <span className="muted" style={{ width: 68, flex: '0 0 auto' }}>{k}</span>
          <span className="muted2 fill" style={{ textAlign: 'right' }}>{v}</span>
        </div>
      ))}
      {o.call && (
        <div className="row gap8 sm vcenter">
          <span className="muted" style={{ width: 68, flex: '0 0 auto' }}>接口</span>
          <span className="mono xs fill" style={{ color: 'var(--ink-3)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis' }}>{o.call}</span>
        </div>
      )}
      <div className="divln" />
      <div className="row between vcenter">
        <span className="eyebrow">安全策略</span>
        <Chip ic="puzzle">策略引擎</Chip>
      </div>
      <Note>执行前自动校验：当数据来源不可信时，系统会拒绝执行，保障操作安全。</Note>
      {role === 'admin' ? (
        o.status === 'pending' ? (
          <div className="row gap8" style={{ marginTop: 2 }}>
            <Btn sz="sm" k="go" ic="check" disabled={publish.isPending}
              onClick={() => publish.mutate(o.id, { onSuccess: () => toast(`已上线「${opTitle(o)}」`) })}>批准上线</Btn>
            <Btn sz="sm" k="ghost" disabled={disable.isPending}
              onClick={() => disable.mutate(o.id, { onSuccess: () => toast(`已停用「${opTitle(o)}」`, 'warn') })}>停用</Btn>
          </div>
        ) : o.status === 'active' ? (
          <div className="row vcenter gap6 sm" style={{ color: 'var(--cap-trusted)', marginTop: 2 }}>
            <Icon n="check" s={14} c="var(--cap-trusted)" />已上线
            <Btn sz="sm" k="ghost" disabled={disable.isPending}
              onClick={() => disable.mutate(o.id, { onSuccess: () => toast(`已停用「${opTitle(o)}」`, 'warn') })}>停用</Btn>
          </div>
        ) : (
          <Btn sz="sm" k="go" ic="check" disabled={publish.isPending}
            onClick={() => publish.mutate(o.id, { onSuccess: () => toast(`已重新上线「${opTitle(o)}」`) })}>重新上线</Btn>
        )
      ) : (
        <div className="row vcenter gap6 sm muted" style={{ marginTop: 2 }}>
          <Icon n="eye" s={14} c="var(--ink-3)" />只读 · 审核需管理员
        </div>
      )}
      <Note>读操作自动上线，写操作需管理员审核后上线。</Note>
    </div>
  );
}
