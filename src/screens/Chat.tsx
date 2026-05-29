import { useState, useEffect } from 'react';
import { useApp } from '../lib/appContext';
import { CHAT, PLLLM_CODE } from '../lib/data';
import { Btn, Chip, Dot, Icon, Note, Tag } from '../components/kit';
import type { ChatPlan } from '../lib/types';

/* ---- PlanCard ---- */
function PlanCard({ c }: { c: ChatPlan }) {
  return (
    <div className="card pad12 col gap8">
      <div className="row between vcenter">
        <span className="eyebrow">📋 执行计划 · execution plan</span>
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
  const { role } = useApp();
  const c = CHAT[role] ?? CHAT.employee;
  const [done, setDone] = useState(false);

  useEffect(() => { setDone(false); }, [role]);

  return (
    <div
      className="col gap12 fill"
      style={{ padding: '16px 18px', justifyContent: 'flex-end' }}
    >
      {/* customer-channel chip */}
      {role === 'customer' && (
        <div className="row vcenter gap6" style={{ alignSelf: 'flex-start' }}>
          <Tag k="trusted">客户通道</Tag>
          <span className="xs muted">仅限你自己的数据</span>
        </div>
      )}

      {/* user message */}
      <div className="msg u">{c.q}</div>

      {/* agent reply block */}
      <div className="col gap8" style={{ maxWidth: '82%' }}>
        <div className="msg a" style={{ maxWidth: '100%' }}>
          {done
            ? c.done
            : `我将执行以下操作，涉及 ${c.writes} 个写操作，需要你确认：`}
        </div>

        {/* policy note (customer only, pre-confirm) */}
        {c.note && !done && (
          <div className="row vcenter gap6 xs" style={{ color: 'var(--cap-data)' }}>
            <Icon n="lock" s={12} c="var(--cap-data)" />
            {c.note}
          </div>
        )}

        {/* plan card always visible */}
        <PlanCard c={c} />

        {/* action buttons / completion message */}
        {done ? (
          <div className="row vcenter gap8 sm" style={{ color: 'var(--cap-trusted)' }}>
            <Icon n="check" s={15} c="var(--cap-trusted)" />
            已确认并执行 · 142ms ·{' '}
            <span className="muted">DATAFLOW_SNAPSHOT 已写入审计链</span>
          </div>
        ) : (
          <div className="row gap8">
            <Btn k="go" ic="check" onClick={() => setDone(true)}>确认执行</Btn>
            <Btn ic="code">修改</Btn>
            <Btn k="ghost">取消</Btn>
          </div>
        )}
      </div>

      {/* input field */}
      <div className="field lg" style={{ marginTop: 4 }}>
        <Icon n="chat" s={15} c="var(--ink-4)" />
        <span>继续输入…</span>
        <div style={{ flex: 1 }} />
        <Icon n="bolt" s={15} c="var(--accent)" />
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
      {/* header */}
      <div
        className="pad14 row between vcenter"
        style={{ borderBottom: '1px solid var(--line-2)' }}
      >
        <span className="h3">P-LLM 生成的代码</span>
        <Tag k="q">只读</Tag>
      </div>

      {/* code block */}
      <div className="pad12 fill">
        <div className="code fill">
          {segments.map((seg, i) =>
            seg.cls ? (
              <span key={i} className={seg.cls}>{seg.text}</span>
            ) : (
              <span key={i}>{seg.text}</span>
            )
          )}
        </div>
      </div>

      {/* footer note */}
      <div className="pad12" style={{ borderTop: '1px solid var(--line-2)' }}>
        <Note>
          {role === 'customer'
            ? '客户角色 → Policy 把 user_id 强制改回本人'
            : 'P-LLM 只看自己写的代码 · 看不到变量内容'}
        </Note>
      </div>
    </div>
  );
}
