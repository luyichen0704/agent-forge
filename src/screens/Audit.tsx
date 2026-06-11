import { useEffect } from 'react';
import { Tag, Dot, Btn, Icon } from '../components/kit';
import { useApp } from '../lib/appContext';
import { useMe } from '../features/auth';
import { useTraces, useTraceAudit, useExecutions, useRollback } from '../features/traces';

function useActiveTrace() {
  const { traceSel, setTraceSel } = useApp();
  const traces = useTraces();
  useEffect(() => {
    if (!traceSel && traces.data?.items.length) setTraceSel(traces.data.items[0].id);
  }, [traceSel, traces.data, setTraceSel]);
  return traceSel ?? traces.data?.items[0]?.id;
}

export function AuditMain() {
  const traceId = useActiveTrace();
  const { data, isLoading } = useTraceAudit(traceId);

  if (isLoading) return <div className="pad16 muted sm">加载审计链…</div>;
  if (!data || data.events.length === 0) return <div className="pad16 muted sm">暂无审计事件。</div>;

  const v = data.verification;
  return (
    <div className="pad16 fill scroll" data-tour="audit-chain">
      <div className="row vcenter gap8" style={{ marginBottom: 12 }}>
        <Tag k={v.valid ? 'trusted' : 'write'}>{v.valid ? 'hash 链完整性已验证' : '链已被篡改'}</Tag>
        <span className="xs muted tnum">{v.count} 事件 · head {v.head?.slice(0, 10)}…</span>
      </div>
      <div className="card pad16">
        <div className="col">
          {data.events.map((ev, i) => (
            <div key={ev.seq} className="row gap10" style={{ alignItems: 'stretch' }}>
              <div className="col vcenter" style={{ width: 16, flex: '0 0 auto' }}>
                <Dot k={ev.cap} />
                {i < data.events.length - 1 && <div className="edge fill" style={{ width: 2, marginTop: 2 }} />}
              </div>
              <div className="col gap2" style={{ paddingBottom: 12 }}>
                <div className="row vcenter gap8">
                  <span className="mono b xs" style={{ color: 'var(--ink)' }}>{ev.event}</span>
                  {ev.event === 'OPERATION_EXECUTED' && <Tag k="write">mutation</Tag>}
                </div>
                <span className="xs muted">{JSON.stringify(ev.payload)}</span>
                <span className="xs mono" style={{ color: 'var(--ink-4)' }}>
                  hash {ev.hash.slice(0, 8)}… ← prev {ev.prev_hash.slice(0, 8)}…
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function AuditAside() {
  const { traceSel, toast } = useApp();
  const role = useMe().data?.acting_role ?? 'admin';
  const canRollback = role === 'employee' || role === 'admin';
  const { data } = useExecutions(traceSel ?? undefined);
  const rollback = useRollback(traceSel ?? undefined);
  const ex = data?.items.find((e) => e.status === 'ok') ?? data?.items[0];

  return (
    <div className="col fill">
      <div className="pad14" style={{ borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3">{ex ? ex.op_key : '执行详情'}</span>
      </div>
      <div className="col gap10 pad14 fill scroll">
        {!ex && <span className="muted sm">该 trace 暂无执行记录。</span>}
        {ex && (
          <>
            <span className="eyebrow">before → after</span>
            <div className="code">{JSON.stringify(ex.before, null, 1)}{'\n→\n'}{JSON.stringify(ex.after, null, 1)}</div>
            <div className="divln" />
            <div className="row between sm"><span className="muted">executor</span><span className="mono muted2">{ex.executor}</span></div>
            <div className="row between sm"><span className="muted">耗时</span><span className="mono muted2">{ex.latency_ms}ms</span></div>
            <div className="row between sm"><span className="muted">状态</span><span className="mono muted2">{ex.status}</span></div>
            {canRollback && ex.status !== 'rolled_back' && (
              <Btn sz="sm" k="warn" ic="refresh" style={{ marginTop: 4 }} disabled={rollback.isPending}
                data-tour="audit-rollback"
                onClick={() => rollback.mutate(ex.id, {
                  onSuccess: () => toast('已回滚 · 已记录补偿事件', 'warn'),
                  onError: (e) => toast((e as Error).message, 'warn'),
                })}>回滚此操作 rollback</Btn>
            )}
            {ex.status === 'rolled_back' && (
              <div className="row vcenter gap6 sm muted"><Icon n="check" s={13} />已回滚</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
