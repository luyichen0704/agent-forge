import { useEffect, useRef, useState } from 'react';
import { useApp } from '../lib/appContext';
import { Btn, Dot, Icon, Note, Tag } from '../components/kit';
import {
  useSessions, useEnsureSession, useMessages, useSendMessage, useConfirmPlan, useCancelPlan,
} from '../features/chat';
import { useSources } from '../features/sources';
import { useQueryClient } from '@tanstack/react-query';
import type { DataSource, Plan } from '../api/types';
import { confirmLabel, capLabel, opTitle, stepKindLabel } from '../lib/labels';
import { shortSourceName, relTime } from '../lib/format';
import { setSessionMeta, getSessionMeta } from '../lib/sessionMeta';

const capDot = (c: string) => (c === 'query' ? 'data' : c === 'parse' ? 'parsed' : 'write');

/* Context-aware example prompts (suggestions the user can one-click fill). */
function examplePrompts(sourceName: string | null): string[] {
  if (!sourceName) {
    return ['查询最近的订单记录', '看看有哪些待处理的任务', '列出系统里的用户'];
  }
  const s = shortSourceName(sourceName);
  return [`在 ${s} 里查一下最近的记录`, `${s} 里都有哪些数据？`, `列出我在 ${s} 中能查看的内容`];
}

function PlanCard({ plan }: { plan: Plan }) {
  return (
    <div className="card pad12 col gap8" data-tour="plan-card">
      <div className="row between vcenter">
        <span className="eyebrow">执行计划 · {confirmLabel(plan.required_confirm_level)}</span>
        <Tag k="m">{plan.writes} 项写操作</Tag>
      </div>
      {plan.steps.map((s) => (
        <div key={s.step_no} className="row vcenter gap8" style={{ fontSize: 12 }}>
          <span className="mono muted xs" style={{ width: 14 }}>{s.step_no}</span>
          <Dot k={capDot(s.kind)} />
          <span className="fill muted2">{s.label}</span>
          {s.kind === 'write' && <Tag k="write">写操作</Tag>}
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

function sessionOptionLabel(id: string, title: string): string {
  const meta = getSessionMeta(id);
  const sys = meta?.sourceName ? shortSourceName(meta.sourceName) : '所有系统';
  const when = meta?.createdAt ? ` · ${relTime(meta.createdAt)}` : '';
  const t = (title || '新会话').slice(0, 18);
  return `${t} · ${sys}${when}`;
}

export function ChatMain() {
  const { setTraceSel, toast, chatSession, setChatSession } = useApp();
  const qc = useQueryClient();
  const sessions = useSessions();
  const sourcesQ = useSources();
  const ensure = useEnsureSession();
  const sessionId = chatSession ?? undefined;
  const [draft, setDraft] = useState('');
  const [scope, setScope] = useState<string>(''); // '' = 所有系统, else source id
  const endRef = useRef<HTMLDivElement>(null);

  const sources: DataSource[] = sourcesQ.data?.items ?? [];

  // pick or create a session (shared via context so the aside sees the same one)
  useEffect(() => {
    if (sessionId || sessions.isLoading) return;
    const first = sessions.data?.items[0];
    if (first) setChatSession(first.id);
    else if (!ensure.isPending) ensure.mutate(undefined, { onSuccess: (s) => setChatSession(s.id) });
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

  function newSession() {
    const src = sources.find((s) => s.id === scope);
    ensure.mutate({ source_id: scope || undefined }, {
      onSuccess: (s) => {
        setSessionMeta(s.id, { sourceId: scope || null, sourceName: src?.name ?? null, createdAt: Date.now() });
        setChatSession(s.id);
        qc.invalidateQueries({ queryKey: ['chat', 'sessions'] });
        toast(scope ? `已新建对话 · 只在「${shortSourceName(src?.name)}」内规划` : '已新建对话 · 未限定系统', 'ok');
      },
      onError: (e) => toast(`新建失败：${(e as Error).message}`, 'warn'),
    });
  }

  function doSend() {
    const text = draft.trim();
    if (!text || !sessionId || send.isPending) return;
    setDraft('');
    send.mutate(text, { onError: (e) => toast(`发送失败：${(e as Error).message}`, 'warn') });
  }

  const items = messages.data?.items ?? [];
  const curMeta = sessionId ? getSessionMeta(sessionId) : undefined;
  const curSourceName = curMeta?.sourceName ?? null;
  const sessionList = sessions.data?.items ?? [];

  return (
    <div className="col fill" style={{ minHeight: 0 }}>
      {/* session + system scope bar */}
      <div className="chat-bar">
        <div className="row vcenter gap8 fill" style={{ minWidth: 0 }}>
          <Icon n="chat" s={14} c="var(--ink-4)" />
          {sessionList.length > 0 ? (
            <select className="sel" aria-label="切换会话" value={sessionId ?? ''}
              onChange={(e) => setChatSession(e.target.value)} style={{ maxWidth: 260 }}>
              {sessionList.map((s) => (
                <option key={s.id} value={s.id}>{sessionOptionLabel(s.id, s.title)}</option>
              ))}
            </select>
          ) : <span className="sm muted">新对话</span>}
          <span className={`scope-chip ${curSourceName ? 'on' : ''}`}>
            <Dot k={curSourceName ? 'data' : 'off'} />
            {curSourceName ? `只在 ${shortSourceName(curSourceName)} 内规划` : '未限定系统'}
          </span>
        </div>
        <div className="row vcenter gap6" style={{ flex: '0 0 auto' }}>
          <select className="sel" aria-label="选择系统范围" value={scope}
            onChange={(e) => setScope(e.target.value)} style={{ maxWidth: 200 }}
            title="新建对话时限定只在该系统的操作里规划">
            <option value="">所有系统（不限定）</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>{shortSourceName(s.name)}</option>
            ))}
          </select>
          <Btn sz="sm" k="pri" ic="plus" disabled={ensure.isPending} onClick={newSession}>新建对话</Btn>
        </div>
      </div>

      <div className="col gap12 fill scroll" style={{ padding: '16px 18px' }}>
        {messages.isLoading && <span className="muted sm">加载会话…</span>}
        {items.length === 0 && !messages.isLoading && (
          <div className="col center fill gap12 muted" style={{ maxWidth: 460, margin: '0 auto', textAlign: 'center' }}>
            <span style={{ width: 46, height: 46, borderRadius: 12, background: 'var(--accent-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon n="chat" s={22} c="var(--accent-ink)" />
            </span>
            <div className="col gap4">
              <span className="h3" style={{ color: 'var(--ink)' }}>用自然语言下达指令</span>
              <span className="sm">
                {curSourceName
                  ? `当前对话已限定在「${shortSourceName(curSourceName)}」，系统只会在该系统的操作里规划。`
                  : '建议先在右上角选择一个系统再新建对话，避免在全部操作里混选。也可以直接提问。'}
              </span>
            </div>
            <div className="col gap6" style={{ width: '100%' }}>
              <span className="eyebrow" style={{ alignSelf: 'flex-start' }}>试试这样问</span>
              {examplePrompts(curSourceName).map((q, i) => (
                <button key={i} className="example-chip" onClick={() => setDraft(q)}>
                  <Icon n="spark" s={13} c="var(--accent)" /><span className="fill" style={{ textAlign: 'left' }}>{q}</span>
                  <Icon n="chevron" s={12} c="var(--ink-4)" />
                </button>
              ))}
            </div>
          </div>
        )}
        {items.map((m) => (
          <div key={m.id} className="col gap8" style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '82%' }}>
            <div className={`msg ${m.role === 'user' ? 'u' : 'a'}`} style={{ maxWidth: '100%', whiteSpace: 'pre-wrap' }}>{m.content}</div>
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
            placeholder={send.isPending ? '正在规划…' : '继续输入指令…'} aria-label="对话输入" disabled={send.isPending}
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
  const meta = chatSession ? getSessionMeta(chatSession) : undefined;

  const latestPlan = (() => {
    const items = messages.data?.items ?? [];
    for (let i = items.length - 1; i >= 0; i--) if (items[i].plan) return items[i].plan!;
    return null;
  })();

  return (
    <div className="col fill">
      <div className="pad14 row between vcenter" style={{ borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3">执行计划详情</span>
        <Tag k="q">只读</Tag>
      </div>
      <div className="pad14 col gap10 fill scroll">
        <div className="row vcenter gap6 sm">
          <Icon n="layers" s={13} c="var(--ink-4)" />
          <span className="muted">规划范围</span>
          <span className="fill" />
          <span className="b" style={{ color: meta?.sourceName ? 'var(--cap-data)' : 'var(--ink-3)' }}>
            {meta?.sourceName ? shortSourceName(meta.sourceName) : '所有系统'}
          </span>
        </div>
        <div className="divln" />
        {!latestPlan && <span className="muted sm">发送指令后，这里会显示系统生成的执行计划与数据说明。</span>}
        {latestPlan && (
          <>
            <span className="eyebrow">意图</span>
            <span className="sm muted2">{latestPlan.intent}</span>
            <div className="divln" />
            <span className="eyebrow">步骤与数据</span>
            {latestPlan.steps.map((s) => (
              <div key={s.step_no} className="row vcenter gap8 sm muted2">
                <Dot k={capDot(s.kind)} />
                <span className="mono xs" style={{ width: 14 }}>{s.step_no}</span>
                <span className="fill">{s.label?.trim() || (s.op_key ? opTitle({ op_key: s.op_key }) : stepKindLabel(s.kind))}</span>
                <Tag k={s.capability_out}>{capLabel(s.capability_out)}</Tag>
              </div>
            ))}
            {latestPlan.policy_hints.length > 0 && (
              <>
                <div className="divln" />
                <span className="eyebrow">策略提示</span>
                {latestPlan.policy_hints.map((h, i) => <span key={i} className="xs muted">· {h}</span>)}
              </>
            )}
            <Note>系统只生成执行计划，看不到具体数据；写操作需经策略校验与人工确认后才执行。</Note>
          </>
        )}
      </div>
    </div>
  );
}
