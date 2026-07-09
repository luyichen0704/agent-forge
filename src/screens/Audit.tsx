import { useEffect } from 'react';
import { Tag, Dot, Btn, Icon } from '../components/kit';
import { useApp } from '../lib/appContext';
import { useMe } from '../features/auth';
import { useTraces, useTraceAudit, useExecutions, useRollback } from '../features/traces';
import { eventLabel, opTitle, executorLabel, execStatusLabel, auditPayloadSummary } from '../lib/labels';

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
  if (!data || data.events.length === 0) {
    return (
      <div className="pad16 col center fill gap8 muted sm" style={{ textAlign: 'center' }}>
        <Icon n="shield" s={28} c="var(--ink-4)" />
        <span>暂无审计记录。</span>
        <span className="xs">在「对话」里执行一次操作后，这里会出现不可篡改的记录链。</span>
      </div>
    );
  }

  const v = data.verification;
  const ok = v.valid;
  return (
    <div className="pad16 fill scroll col gap12" data-tour="audit-chain">
      {/* integrity banner */}
      <div className={`audit-banner ${ok ? 'ok' : 'bad'}`}>
        <span className="ab-mark">
          <Icon n={ok ? 'shield' : 'x'} s={20} c="var(--on-cap)" />
        </span>
        <div className="col fill" style={{ gap: 2 }}>
          <span className="b" style={{ fontSize: 13, color: ok ? 'var(--cap-trusted-ink)' : 'var(--danger-ink)' }}>
            {ok ? '完整性已验证' : `记录在第 ${v.broken_at_seq} 环被篡改`}
          </span>
          <span className="xs muted">
            {ok
              ? `${v.count} 条记录环环相扣，任何篡改都会被立即发现`
              : '哈希链校验未通过，请立即排查'}
          </span>
        </div>
        <Tag k={ok ? 'trusted' : 'write'}>{ok ? '✓ 可信' : '⚠ 异常'}</Tag>
      </div>

      <div className="card pad16">
        <div className="col">
          {data.events.map((ev, i) => (
            <div key={ev.seq} className="row gap10" style={{ alignItems: 'stretch' }}>
              <div className="col vcenter" style={{ width: 18, flex: '0 0 auto' }}>
                <span className="audit-node"><Dot k={ev.cap} /></span>
                {i < data.events.length - 1 && <div className="edge fill" style={{ width: 2, marginTop: 2 }} />}
              </div>
              <div className="col gap2" style={{ paddingBottom: 14, minWidth: 0 }}>
                <div className="row vcenter gap8">
                  <span className="xs mono muted" style={{ minWidth: 20 }}>#{ev.seq}</span>
                  <span className="b xs" style={{ color: 'var(--ink)' }}>{eventLabel(ev.event)}</span>
                  {ev.event === 'OPERATION_EXECUTED' && <Tag k="write">写操作</Tag>}
                </div>
                {auditPayloadSummary(ev.payload) && <span className="xs muted">{auditPayloadSummary(ev.payload)}</span>}
                <span className="xs mono row vcenter gap5" style={{ color: 'var(--ink-4)' }}>
                  <Icon n="lock" s={10} c="var(--cap-trusted)" />
                  校验码 {ev.hash.slice(0, 8)}… · 承接 {ev.prev_hash.slice(0, 8)}…
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
        <span className="h3">{ex ? opTitle(ex) : '执行详情'}</span>
      </div>
      <div className="col gap10 pad14 fill scroll">
        {!ex && <span className="muted sm">这条记录暂无执行明细。</span>}
        {ex && (
          <>
            <span className="eyebrow">执行前 → 执行后</span>
            <div className="code">{JSON.stringify(ex.before, null, 1)}{'\n→\n'}{JSON.stringify(ex.after, null, 1)}</div>
            <div className="divln" />
            <div className="row between sm"><span className="muted">执行方式</span><span className="muted2">{executorLabel(ex.executor)}</span></div>
            <div className="row between sm"><span className="muted">耗时</span><span className="mono muted2">{ex.latency_ms}ms</span></div>
            <div className="row between sm"><span className="muted">状态</span><span className="muted2">{execStatusLabel(ex.status)}</span></div>
            {canRollback && ex.status !== 'rolled_back' && (
              <Btn sz="sm" k="warn" ic="refresh" style={{ marginTop: 4 }} disabled={rollback.isPending}
                data-tour="audit-rollback"
                onClick={() => rollback.mutate(ex.id, {
                  onSuccess: () => toast('已回滚 · 已记录补偿操作', 'warn'),
                  onError: (e) => toast((e as Error).message, 'warn'),
                })}>回滚此操作</Btn>
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
