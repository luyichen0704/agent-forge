import { Tag, Dot, Btn } from '../components/kit';
import { AUDIT_EVENTS } from '../lib/data';
import { useApp } from '../lib/appContext';

export function AuditMain() {
  return (
    <div className="pad16 fill scroll">
      <div className="card pad16">
        <div className="col">
          {AUDIT_EVENTS.map((ev, i) => (
            <div key={i} className="row gap10" style={{ alignItems: 'stretch' }}>
              <div className="col vcenter" style={{ width: 16, flex: '0 0 auto' }}>
                <Dot k={ev.cap} />
                {i < AUDIT_EVENTS.length - 1 && (
                  <div className="edge fill" style={{ width: 2, marginTop: 2 }} />
                )}
              </div>
              <div className="col gap2" style={{ paddingBottom: 12 }}>
                <div className="row vcenter gap8">
                  <span className="mono b xs" style={{ color: 'var(--ink)' }}>{ev.event}</span>
                  {ev.event === 'OPERATION_EXECUTED' && <Tag k="write">mutation</Tag>}
                </div>
                <span className="xs muted">{ev.detail}</span>
                <span className="xs mono" style={{ color: 'var(--ink-4)' }}>
                  hash 9f3a… ← prev e21c…
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
  const { toast } = useApp();
  return (
    <div className="col fill">
      <div className="pad14" style={{ borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3">OPERATION_EXECUTED</span>
      </div>
      <div className="col gap10 pad14 fill scroll">
        <span className="eyebrow">before → after diff</span>
        <div className="code">
          {'refund_status:\n  '}
          <span className="c">- pending</span>
          {'\n  '}
          <span className="s">+ expedited</span>
          {'\namount: ¥299'}
        </div>
        <div className="divln" />
        <div className="row between sm">
          <span className="muted">executor</span>
          <span className="mono muted2">APIExecutor</span>
        </div>
        <div className="row between sm">
          <span className="muted">耗时</span>
          <span className="mono muted2">142ms</span>
        </div>
        <Btn sz="sm" k="warn" ic="refresh" style={{ marginTop: 4 }} onClick={() => toast('已回滚 refund.expedite · 已记录补偿事件', 'warn')}>回滚此操作 rollback</Btn>
      </div>
    </div>
  );
}
