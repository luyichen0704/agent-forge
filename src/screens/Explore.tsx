import { Icon, Btn, Tag, Dot, Note } from '../components/kit';
import { DATA_SOURCES, EXPLORE_PHASES } from '../lib/data';
import { useApp } from '../lib/appContext';

/* subnav rows 1..5 map onto DATA_SOURCES */
const PHASE_NUM = ['1', '2', '3', '4'];

/* ---- ExploreMain: 5 source cards ---- */
export function ExploreMain() {
  const { treeSel, setTreeSel, toast } = useApp();

  return (
    <div className="col gap10 fill scroll" style={{ padding: 16 }}>
      {DATA_SOURCES.map((s, i) => {
        const selected = treeSel === i + 1;
        return (
          <div
            key={i}
            className={`card hover row vcenter gap12 ${selected ? '' : ''}`}
            style={{
              padding: 12,
              cursor: 'pointer',
              borderColor: selected ? 'var(--accent)' : 'var(--line)',
              boxShadow: selected ? '0 0 0 1px var(--accent)' : undefined,
            }}
            role="button"
            tabIndex={0}
            onClick={() => setTreeSel(i + 1)}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTreeSel(i + 1); } }}
          >
            <span style={iconBox}>
              <Icon n={s.icon} s={18} c="var(--ink-2)" />
            </span>

            <div className="col" style={{ width: 150 }}>
              <span className="b sm">{s.label}</span>
              <span className="xs muted mono">{s.conn}</span>
            </div>

            <div className="fill">
              {s.dotKind === 'wait' && s.progress != null && (
                <div className="prog" style={{ maxWidth: 220 }}>
                  <i style={{ width: `${s.progress}%` }} />
                </div>
              )}
            </div>

            <div className="row vcenter gap6 sm muted2">
              <Dot k={s.dotKind} />
              {s.statusLabel}
            </div>

            <Icon n="dots" s={16} c="var(--ink-4)" />
          </div>
        );
      })}

      {/* add new explorer card */}
      <div className="card row vcenter gap12" style={{ padding: 12, borderStyle: 'dashed', background: 'var(--fill-2)' }}>
        <span style={{ ...iconBox, background: 'var(--accent-soft)' }}>
          <Icon n="puzzle" s={18} c="var(--accent-ink)" />
        </span>
        <div className="col fill">
          <span className="b sm">接入新探索器 Explorer 插件</span>
          <span className="xs muted">实现 Explorer 接口即可挂载任意数据源（gRPC、消息队列、SaaS…）</span>
        </div>
        <Btn sz="sm" ic="plus" onClick={() => toast('打开插件市场（演示）', 'info')}>添加</Btn>
      </div>
    </div>
  );
}

const iconBox: React.CSSProperties = {
  width: 34, height: 34, borderRadius: 8, background: 'var(--fill)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
};

/* ---- ExploreAside: selected explorer panel ---- */
export function ExploreAside() {
  const { treeSel } = useApp();
  const idx = treeSel >= 1 && treeSel <= DATA_SOURCES.length ? treeSel - 1 : 0;
  const src = DATA_SOURCES[idx];
  const names = ['CodeExplorer', 'DatabaseExplorer', 'APIExplorer', 'AdminPanelExplorer', 'DocExplorer'];
  const name = names[idx] ?? 'CodeExplorer';
  const active = src.dotKind !== 'wait';

  return (
    <div className="col fill">
      <div className="row between vcenter" style={{ padding: '12px 14px', borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3 mono">{name}</span>
        <Tag k={active ? 'trusted' : 'parsed'}>{active ? 'active' : 'running'}</Tag>
      </div>

      <div className="col gap12 fill scroll" style={{ padding: 14 }}>
        <div className="col gap6">
          <span className="eyebrow">连接 Connector</span>
          <div className="field" style={{ gap: 0 }}>
            <span className="mono xs" style={{ color: 'var(--ink-2)' }}>{src.conn}</span>
          </div>
        </div>

        <div className="col gap8">
          <span className="eyebrow">探索阶段 Phases</span>
          {EXPLORE_PHASES.map((p, i) => (
            <div key={i} className="row vcenter gap8 sm muted2">
              <Dot k={p.state === 'done' ? 'ok' : p.state === 'now' ? 'wait' : 'off'} />
              <span className="mono xs" style={{ color: 'var(--ink-4)', width: 10 }}>{PHASE_NUM[i]}</span>
              <span className="fill">{p.sub}</span>
              {p.state === 'done' && <Icon n="check" s={13} c="var(--cap-trusted)" />}
            </div>
          ))}
        </div>

        <div className="divln" />

        <span className="eyebrow">实现接口 implements</span>
        <div className="code">
          {'class Explorer(ABC):\n  async def '}
          <span className="f">explore</span>
          {'(self,\n    src) -> list['}
          <span className="v">OperationDraft</span>
          {']'}
        </div>

        <Note>换数据源 = 新写一个 Explorer 即可，内核不变。</Note>
      </div>
    </div>
  );
}
