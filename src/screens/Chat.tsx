import { useState, useEffect, useRef } from 'react';
import { useApp } from '../lib/appContext';
import { CHAT, PLLLM_CODE } from '../lib/data';
import { Btn, Dot, Icon, Note, Tag } from '../components/kit';
import type { ChatPlan } from '../lib/types';

interface Msg { who: 'u' | 'a'; text: string; }

/* ---- PlanCard ---- */
function PlanCard({ c }: { c: ChatPlan }) {
  return (
    <div className="card pad12 col gap8">
      <div className="row between vcenter">
        <span className="eyebrow">执行计划 · execution plan</span>
        <Tag k="m">{c.writes} 写操作</Tag>
      </div>
      {c.plan.map(([n, t, k], i) => (
        <div key={i} className="row vcenter gap8" style={{ fontSize: 12 }}>
          <span className="mono muted xs" style={{ width: 14 }}>{n}</span>
          <Dot k={k === 'q' ? 'data' : k === 'p' ? 'parsed' : 'write'} />
          <span className="fill muted2">{t}</span>
          {k === 'm' && <Tag k="write">mutation</Tag>}
        </div>
      ))}
      <div className="divln" />
      <div className="row vcenter gap6 xs muted">
        <Icon n="bolt" s={12} c="var(--cap-write)" />
        {c.foot}
      </div>
    </div>
  );
}

/* ---- ChatMain ---- */
export function ChatMain() {
  const { role, toast } = useApp();
  const c = CHAT[role] ?? CHAT.employee;
  const [done, setDone] = useState(false);
  const [extra, setExtra] = useState<Msg[]>([]);
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setDone(false); setExtra([]); }, [role]);
  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: 'smooth' }); }, [extra, done]);

  function send() {
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    setExtra(prev => [...prev, { who: 'u', text }]);
    setTimeout(() => {
      setExtra(prev => [...prev, {
        who: 'a',
        text: 'P-LLM 已把这条指令编译成新计划草稿，读操作自动执行，写操作会先弹确认。（演示）',
      }]);
    }, 450);
  }

  return (
    <div className="col fill" style={{ minHeight: 0 }}>
      {/* conversation */}
      <div className="col gap12 fill scroll" style={{ padding: '16px 18px' }}>
        {role === 'customer' && (
          <div className="row vcenter gap6" style={{ alignSelf: 'flex-start' }}>
            <Tag k="trusted">客户通道</Tag>
            <span className="xs muted">仅限你自己的数据</span>
          </div>
        )}

        <div className="msg u">{c.q}</div>

        <div className="col gap8" style={{ maxWidth: '82%' }}>
          <div className="msg a" style={{ maxWidth: '100%' }}>
            {done ? c.done : `我将执行以下操作，涉及 ${c.writes} 个写操作，需要你确认：`}
          </div>

          {c.note && !done && (
            <div className="row vcenter gap6 xs" style={{ color: 'var(--cap-data)' }}>
              <Icon n="lock" s={12} c="var(--cap-data)" />
              {c.note}
            </div>
          )}

          <PlanCard c={c} />

          {done ? (
            <div className="row vcenter gap8 sm" style={{ color: 'var(--cap-trusted)' }}>
              <Icon n="check" s={15} c="var(--cap-trusted)" />
              已确认并执行 · 142ms ·{' '}
              <span className="muted">DATAFLOW_SNAPSHOT 已写入审计链</span>
            </div>
          ) : (
            <div className="row gap8">
              <Btn k="go" ic="check" onClick={() => { setDone(true); toast('操作已执行，已写入审计链'); }}>确认执行</Btn>
              <Btn ic="code" onClick={() => toast('打开计划编辑器（演示）', 'info')}>修改</Btn>
              <Btn k="ghost" onClick={() => toast('已取消', 'warn')}>取消</Btn>
            </div>
          )}
        </div>

        {/* user-appended messages */}
        {extra.map((m, i) => (
          <div key={i} className={`msg ${m.who}`}>{m.text}</div>
        ))}
        <div ref={endRef} />
      </div>

      {/* input */}
      <div style={{ padding: '12px 18px', borderTop: '1px solid var(--line)', background: 'var(--paper)', flexShrink: 0 }}>
        <label className="field lg">
          <Icon n="chat" s={15} c="var(--ink-4)" />
          <input
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') send(); }}
            placeholder="继续输入指令…"
            aria-label="对话输入"
          />
          <button
            className="btn pri sm"
            onClick={send}
            disabled={!draft.trim()}
            aria-label="发送"
            style={{ height: 28 }}
          >
            <Icon n="bolt" s={13} c="#fff" /> 发送
          </button>
        </label>
      </div>
    </div>
  );
}

/* ---- ChatAside ---- */
export function ChatAside() {
  const { role } = useApp();
  const segments = PLLLM_CODE[role] ?? PLLLM_CODE.employee;

  return (
    <div className="col fill">
      <div className="pad14 row between vcenter" style={{ borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3">P-LLM 生成的代码</span>
        <Tag k="q">只读</Tag>
      </div>

      <div className="pad12 fill">
        <div className="code fill">
          {segments.map((seg, i) =>
            seg.cls ? <span key={i} className={seg.cls}>{seg.text}</span> : <span key={i}>{seg.text}</span>
          )}
        </div>
      </div>

      <div className="pad12" style={{ borderTop: '1px solid var(--line-2)' }}>
        <Note>
          {role === 'customer'
            ? '客户角色 → Policy 把 user_id 强制改回本人。'
            : 'P-LLM 只看自己写的代码，看不到变量内容。'}
        </Note>
      </div>
    </div>
  );
}
