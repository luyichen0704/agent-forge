import { useEffect, useRef, useState } from 'react';
import { Icon, Tag, Dot, Note } from '../components/kit';
import { EXPLORE_PHASES, LIVE_FILES, LIVE_STREAM, LIVE_EXTRACTION } from '../lib/data';

/* ---- Helper: 4-phase timeline ---- */
function Phases() {
  return (
    <div className="col gap8">
      {EXPLORE_PHASES.map((p, i) => (
        <div
          key={i}
          className="row vcenter gap8"
          style={{ fontSize: 12.5, color: p.state === 'todo' ? 'var(--ink-4)' : 'var(--ink-2)' }}
        >
          <Dot k={p.state === 'done' ? 'ok' : p.state === 'now' ? 'wait' : 'off'} />
          <span className="b">{p.label}</span>
          <span className="fill">{p.sub}</span>
          {p.state === 'done' && <Icon n="check" s={13} c="var(--cap-trusted)" />}
          {p.state === 'now' && <span className="xs mono" style={{ color: 'var(--accent)' }}>running</span>}
        </div>
      ))}
    </div>
  );
}

/* ---- LiveMain: phases + file list + streaming log ---- */
export function LiveMain() {
  const [count, setCount] = useState(4);
  const logRef = useRef<HTMLDivElement>(null);

  /* stream new log lines in over time, then loop */
  useEffect(() => {
    const id = setInterval(() => {
      setCount(c => (c >= LIVE_STREAM.length ? 4 : c + 1));
    }, 1400);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [count]);

  const lines = LIVE_STREAM.slice(0, count);

  return (
    <div className="col gap14 fill scroll" style={{ padding: 16 }}>
      <div className="row gap14 wrap">
        <div className="card col gap10" style={{ width: 230, padding: 14 }}>
          <span className="eyebrow">探索阶段</span>
          <Phases />
        </div>

        <div className="card col fill gap8" style={{ padding: 14, minWidth: 280 }}>
          <div className="row between vcenter">
            <span className="eyebrow">正在读取 · reading</span>
            <Tag k="data">phase 2</Tag>
          </div>
          <div className="code fill">
            {LIVE_FILES.map((f, i) => {
              const isActive = i === LIVE_FILES.length - 1;
              return (
                <div key={i} style={{ opacity: isActive ? 1 : 0.5 }}>
                  {isActive ? <span className="s">▸ </span> : '  '}
                  {f}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="card col gap8" style={{ padding: 14 }}>
        <div className="row between vcenter">
          <span className="eyebrow">实时日志 · stream</span>
          <span className="row vcenter gap5 xs muted"><Dot k="wait" /> live</span>
        </div>
        <div ref={logRef} className="code" style={{ maxHeight: 168 }}>
          {lines.map((l, i) => (
            <div key={i}>
              <span className="c">{`[${l.t}] `}</span>
              <span className={l.cls}>{l.tag}</span>
              <span>{l.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---- LiveAside: per-file extraction summary ---- */
export function LiveAside() {
  return (
    <div className="col fill">
      <div style={{ padding: 14, borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3">本文件提取</span>
      </div>

      <div className="col gap12 fill scroll" style={{ padding: 14 }}>
        {LIVE_EXTRACTION.map(([k, v], i) => (
          <div key={i} className="col gap3">
            <span className="eyebrow">{k}</span>
            <span className="sm muted2">{v}</span>
          </div>
        ))}

        <div className="divln" />

        <div className="row between">
          <span className="sm muted">生成操作</span>
          <span className="b tnum">23</span>
        </div>
        <div className="row between">
          <span className="sm muted">待审核 (写)</span>
          <Tag k="write">8</Tag>
        </div>

        <div className="divln" />

        <Note ink>读操作自动激活 · 写操作待审核后上线。</Note>
      </div>
    </div>
  );
}
