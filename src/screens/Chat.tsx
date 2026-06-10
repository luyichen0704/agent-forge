import { useEffect, useRef, useState } from 'react';
import { useApp } from '../lib/appContext';
import { Btn, Dot, Icon, Note, Tag } from '../components/kit';
import {
  useSessions, useEnsureSession, useMessages, useSendMessage, useConfirmPlan, useCancelPlan,
} from '../features/chat';
import { useQueryClient } from '@tanstack/react-query';
import type { Plan } from '../api/types';

const capDot = (c: string) => (c === 'query' ? 'data' : c === 'parse' ? 'parsed' : 'write');

function PlanCard({ plan }: { plan: Plan }) {
  return (
    <div className="card pad12 col gap8" data-tour="plan-card">
      <div className="row between vcenter">
        <span className="eyebrow">执行计划 · {plan.required_confirm_level}</span>
        <Tag k="m">{plan.writes} 写操作</Tag>
      </div>
      {plan.steps.map((s) => (
        <div key={s.step_no} className="row vcenter gap8" style={{ fontSize: 12 }}>
          <span className="mono muted xs" style={{ width: 14 }}>{s.step_no}</span>
          <Dot k={capDot(s.kind)} />
          <span className="fill muted2">{s.label}</span>
          {s.kind === 'write' && <Tag k="write">mutation</Tag>}
        </div>
      ))}
      {plan.reasoning_summary && (
        <>
          <div className="divln" />
          <span className="xs muted">{plan.reasoning_summary}</span>
        </>
      )}
    </div>
  );
}

export function ChatMain() {
  const { setTraceSel, toast, chatSession, setChatSession } = useApp();
  const qc = useQueryClient();
  const sessions = useSessions();
  const ensure = useEnsureSession();
  const sessionId = chatSession ?? undefined;
  const setSessionId = (id: string) => setChatSession(id);
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  // pick or create a session (shared via context so the aside sees the same one)
  useEffect(() => {
    if (sessionId || sessions.isLoading) return;
    const first = sessions.data?.items[0];
    if (first) setSessionId(first.id);
    else if (!ensure.isPending) ensure.mutate(undefined, { onSuccess: (s) => setSessionId(s.id) });
  }, [sessions.data, sessions.isLoading, sessionId, ensure, setChatSession]);

  const messages = useMessages(sessionId);
  const send = useSendMessage(sessionId);
  const confirm = useConfirmPlan(sessionId);
  const cancel = useCancelPlan(sessionId);

  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: 'smooth' }); }, [messages.data, send.isPending]);

  // surface the latest plan's trace to Flow/Audit
  useEffect(() => {
    const items = messages.data?.items ?? [];
    for (let i = items.length - 1; i >= 0; i--) {
      if (items[i].plan) { setTraceSel(items[i].plan!.trace_id); break; }
    }
  }, [messages.data, setTraceSel]);

  function doSend() {
    const text = draft.trim();
    if (!text || !sessionId || send.isPending) return;
    setDraft('');
    send.mutate(text, { onError: (e) => toast(`发送失败：${(e as Error).message}`, 'warn') });
  }

  const items = messages.data?.items ?? [];

  return (
    <div className="col fill" style={{ minHeight: 0 }}>
      <div className="col gap12 fill scroll" style={{ padding: '16px 18px' }}>
        {messages.isLoading && <span className="muted sm">加载会话…</span>}
        {items.length === 0 && !messages.isLoading && (
          <div className="col center fill gap8 muted sm">
            <Icon n="chat" s={28} c="var(--ink-4)" />
            用自然语言下达指令，P-LLM 会生成可审计的执行计划。
          </div>
        )}
        {items.map((m) => (
          <div key={m.id} className="col gap8" style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '82%' }}>
            <div className={`msg ${m.role === 'user' ? 'u' : 'a'}`} style={{ maxWidth: '100%' }}>{m.content}</div>
            {m.plan && <PlanCard plan={m.plan} />}
            {m.plan && m.plan.status === 'awaiting_confirm' && (
              <div className="row gap8" data-tour="plan-confirm">
                <Btn k="go" ic="check" disabled={confirm.isPending}
                  onClick={() => confirm.mutate(m.plan!.id, {
                    onSuccess: (p) => toast(p.blocked ? '仍需更多审批' : '已执行并写入审计链', p.blocked ? 'warn' : 'ok'),
                  })}>确认执行</Btn>
                <Btn k="ghost" disabled={cancel.isPending}
                  onClick={() => cancel.mutate(m.plan!.id, { onSuccess: () => toast('已取消', 'warn') })}>取消</Btn>
              </div>
            )}
            {m.plan && m.plan.status === 'done' && (
              <div className="row vcenter gap8 sm" style={{ color: 'var(--cap-trusted)' }} data-tour="plan-done">
                <Icon n="check" s={15} c="var(--cap-trusted)" />已执行 · 已写入审计链
                <button className="btn ghost sm" onClick={() => { setTraceSel(m.plan!.trace_id); qc.invalidateQueries({ queryKey: ['traces'] }); toast('已在审计/数据流中定位该 trace', 'info'); }}>查看审计</button>
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <div style={{ padding: '12px 18px', borderTop: '1px solid var(--line)', background: 'var(--paper)', flexShrink: 0 }}>
        <label className="field lg">
          <Icon n="chat" s={15} c="var(--ink-4)" />
          <input value={draft} onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') doSend(); }}
            placeholder={send.isPending ? 'P-LLM 规划中…' : '继续输入指令…'} aria-label="对话输入" disabled={send.isPending}
            data-tour="chat-input" />
          <button className="btn pri sm" onClick={doSend} disabled={!draft.trim() || send.isPending}
            aria-label="发送" style={{ height: 28 }} data-tour="chat-send">
            <Icon n="bolt" s={13} c="#fff" /> 发送
          </button>
        </label>
      </div>
    </div>
  );
}

export function ChatAside() {
  const { chatSession } = useApp();
  const messages = useMessages(chatSession ?? undefined);

  const latestPlan = (() => {
    const items = messages.data?.items ?? [];
    for (let i = items.length - 1; i >= 0; i--) if (items[i].plan) return items[i].plan!;
    return null;
  })();

  return (
    <div className="col fill">
      <div className="pad14 row between vcenter" style={{ borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3">P-LLM 计划详情</span>
        <Tag k="q">只读</Tag>
      </div>
      <div className="pad14 col gap10 fill scroll">
        {!latestPlan && <span className="muted sm">发送指令后，这里显示 P-LLM 生成的结构化计划与能力标注。</span>}
        {latestPlan && (
          <>
            <span className="eyebrow">意图 intent</span>
            <span className="sm muted2">{latestPlan.intent}</span>
            <div className="divln" />
            <span className="eyebrow">步骤能力 capabilities</span>
            {latestPlan.steps.map((s) => (
              <div key={s.step_no} className="row vcenter gap8 sm muted2">
                <Dot k={capDot(s.kind)} />
                <span className="mono xs" style={{ width: 14 }}>{s.step_no}</span>
                <span className="fill">{s.op_key ?? s.kind}</span>
                <Tag k={s.capability_out}>{s.capability_out}</Tag>
              </div>
            ))}
            {latestPlan.policy_hints.length > 0 && (
              <>
                <div className="divln" />
                <span className="eyebrow">策略提示 policy</span>
                {latestPlan.policy_hints.map((h, i) => <span key={i} className="xs muted">· {h}</span>)}
              </>
            )}
            <Note>P-LLM 只产出结构化计划，看不到具体数据；写操作经策略与人审后才执行。</Note>
          </>
        )}
      </div>
    </div>
  );
}
