import { Icon, Btn, Tag, Dot, Note } from '../components/kit';
import { useApp } from '../lib/appContext';
import { useMe } from '../features/auth';
import { useSources, useStartExplore } from '../features/sources';
import { useQueryClient } from '@tanstack/react-query';

const iconBox: React.CSSProperties = {
  width: 34, height: 34, borderRadius: 8, background: 'var(--fill)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
};
const SRC_ICON: Record<string, string> = { code: 'code', db: 'db', api: 'globe', admin: 'table', doc: 'doc' };

export function ExploreMain() {
  const { treeSel, setTreeSel, toast } = useApp();
  const role = useMe().data?.acting_role ?? 'admin';
  const { data, isLoading } = useSources();

  if (isLoading) return <div className="pad16 muted sm">加载数据源…</div>;
  const sources = data?.items ?? [];

  return (
    <div className="col gap10 fill scroll" style={{ padding: 16 }}>
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
              {s.status}
            </div>
            <Icon n="chevron" s={16} c="var(--ink-4)" />
          </div>
        );
      })}
      {role === 'admin' && (
        <div className="card row vcenter gap12" style={{ padding: 12, borderStyle: 'dashed', background: 'var(--fill-2)' }}>
          <span style={{ ...iconBox, background: 'var(--accent-soft)' }}><Icon n="puzzle" s={18} c="var(--accent-ink)" /></span>
          <div className="col fill">
            <span className="b sm">接入新探索器 Explorer 插件</span>
            <span className="xs muted">实现 Explorer 接口即可挂载任意数据源</span>
          </div>
          <Btn sz="sm" ic="plus" onClick={() => toast('打开插件市场（演示）', 'info')}>添加</Btn>
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
        <span className="h3 mono">{src.connector_kind}</span>
        <Tag k={src.status === 'connected' ? 'trusted' : 'parsed'}>{src.status}</Tag>
      </div>
      <div className="col gap12 fill scroll" style={{ padding: 14 }}>
        <div className="col gap6">
          <span className="eyebrow">连接 Connector</span>
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
        <span className="eyebrow">实现接口 implements</span>
        <div className="code">
          {'class Explorer(ABC):\n  async def '}<span className="f">explore</span>
          {'(self,\n    src) -> list['}<span className="v">OperationDraft</span>{']'}
        </div>
        <Note>探索产物会写入操作注册表（读操作自动上线，写操作待审核）。</Note>
      </div>
    </div>
  );
}
