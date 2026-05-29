import { Icon, Tag, Dot, Note } from '../components/kit';
import { EXPLORE_PHASES, LIVE_FILES, LIVE_LOG, LIVE_EXTRACTION } from '../lib/data';

/* ---- Helper: 4-phase timeline ---- */
function Phases() {
  return (
    <div className="col gap6">
      {EXPLORE_PHASES.map((p, i) => (
        <div
          key={i}
          className="row vcenter gap8"
          style={{
            fontSize: 12.5,
            color: p.state === 'todo' ? 'var(--ink-4)' : 'var(--ink-2)',
          }}
        >
          <Dot k={p.state === 'done' ? 'ok' : p.state === 'now' ? 'wait' : 'off'} />
          <span className="b">{p.label}</span>
          <span>{p.sub}</span>
          {p.state === 'done' && <Icon n="check" s={13} c="var(--cap-trusted)" />}
          {p.state === 'now' && (
            <span className="xs" style={{ color: 'var(--accent)' }}>
              ⏳
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

/* ---- LiveMain: 73% progress + phases + file list + log ---- */
export function LiveMain() {
  return (
    <div className="col fill">
      {/* topbar */}
      <div
        className="row between vcenter"
        style={{
          padding: '14px 18px',
          borderBottom: '1px solid var(--line)',
          background: 'var(--paper)',
        }}
      >
        <div className="col">
          <span className="h2">Explorer · 实时探索</span>
          <span className="sm muted">CodeExplorer 正在阅读 company/backend</span>
        </div>
        <div className="row vcenter gap10">
          <span className="sm muted tnum">73%</span>
          <div className="prog" style={{ width: 160 }}>
            <i style={{ width: '73%' }} />
          </div>
        </div>
      </div>

      {/* content */}
      <div className="col gap14 fill" style={{ padding: 16, overflowY: 'auto' }}>
        {/* top row: phases card + file reading card */}
        <div className="row gap14">
          {/* phases */}
          <div className="card col gap10" style={{ width: 230, padding: 14 }}>
            <span className="eyebrow">探索阶段</span>
            <Phases />
          </div>

          {/* reading files */}
          <div className="card col fill gap8" style={{ padding: 14 }}>
            <div className="row between vcenter">
              <span className="eyebrow">正在读取 · reading</span>
              <Tag k="data">phase 2</Tag>
            </div>
            <div className="code fill">
              {LIVE_FILES.map((f, i) => {
                const isActive = i === LIVE_FILES.length - 1;
                return (
                  <div key={i} style={{ opacity: isActive ? 1 : 0.5 }}>
                    {isActive ? <span className="k">▸ </span> : '  '}
                    {f}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* log card */}
        <div className="card col gap8" style={{ padding: 14 }}>
          <span className="eyebrow">实时日志 · stream</span>
          <div className="code">
            {'[12:04:31] '}
            <span className="f">extract</span>
            {' order.py → entity Order, OrderItem\n[12:04:33] '}
            <span className="f">rule</span>
            {'    取消订单需校验 refund_status\n[12:04:34] '}
            <span className="f">chain</span>
            {'   order.cancel → inventory.restore + refund.create\n[12:04:36] '}
            <span className="s">+ op</span>
            {'    order.cancel  '}
            <span className="c">{'// mutation · pending_review'}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---- LiveAside: 本文件提取 extraction rows + counts ---- */
export function LiveAside() {
  return (
    <div className="col fill">
      {/* header */}
      <div
        style={{
          padding: 14,
          borderBottom: '1px solid var(--line-2)',
        }}
      >
        <span className="h3">本文件提取</span>
      </div>

      {/* extraction rows */}
      <div className="col gap10 fill" style={{ padding: 14, overflowY: 'auto' }}>
        {LIVE_EXTRACTION.map(([k, v], i) => (
          <div key={i} className="col gap3">
            <span className="eyebrow">{k}</span>
            <span className="sm muted2">{v}</span>
          </div>
        ))}

        <div className="divln" />

        {/* counts */}
        <div className="row between">
          <span className="sm muted">生成操作</span>
          <span className="b">23</span>
        </div>
        <div className="row between">
          <span className="sm muted">待审核 (写)</span>
          <Tag k="write">8</Tag>
        </div>

        <div className="divln" />

        <Note ink>读操作自动激活 · 写操作待审核后上线</Note>
      </div>
    </div>
  );
}
