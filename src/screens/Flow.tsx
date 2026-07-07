import { useEffect } from 'react';
import { Dot, Note, Sw, Tag, Icon } from '../components/kit';
import { useApp } from '../lib/appContext';
import { useTraces, useTraceFlow } from '../features/traces';
import type { CapKind } from '../api/types';
import { flowNodeLabel, nodeSourceLabel, capLabel } from '../lib/labels';

const LEGEND: Array<[CapKind, string]> = [
  ['trusted', '可信输入 · 你直接提供'],
  ['data', '内部数据 · 系统读取'],
  ['parsed', '解析结果 · AI 提取'],
  ['write', '写操作 · 会改动数据'],
];

function useActiveTrace() {
  const { traceSel, setTraceSel } = useApp();
  const traces = useTraces();
  useEffect(() => {
    if (!traceSel && traces.data?.items.length) setTraceSel(traces.data.items[0].id);
  }, [traceSel, traces.data, setTraceSel]);
  return traceSel ?? traces.data?.items[0]?.id;
}

export function FlowMain() {
  const { flowSel, setFlowSel } = useApp();
  const traceId = useActiveTrace();
  const { data, isLoading } = useTraceFlow(traceId);

  if (isLoading) return <div className="fill center muted sm">加载数据流…</div>;
  if (!data || data.nodes.length === 0) {
    return (
      <div className="fill center col gap8 muted sm" style={{ textAlign: 'center' }}>
        <Icon n="flow" s={28} c="var(--ink-4)" />
        <span>暂无数据流，先在对话里执行一次操作。</span>
      </div>
    );
  }

  const LEGEND_ITEMS: CapKind[] = ['trusted', 'data', 'parsed', 'write'];
  return (
    <div className="fill scroll col vcenter" style={{ background: 'var(--canvas)', padding: 24 }} data-tour="flow-graph">
      <div className="row vcenter gap10 wrap" style={{ marginBottom: 18 }}>
        <span className="eyebrow">数据流向 · {data.nodes.length} 个节点</span>
        <span className="divv" style={{ height: 14 }} />
        {LEGEND_ITEMS.map((c) => (
          <span key={c} className="row vcenter gap5 xs muted"><Dot k={c} />{capLabel(c)}</span>
        ))}
      </div>
      <div className="col center gap2">
        {data.nodes.map((node, i) => (
          <div key={node.node_id} className="col center">
            <button className={`node flow-node ${node.cap} ${i === flowSel ? 'sel' : ''}`}
              style={{ width: 360, justifyContent: 'space-between' }} onClick={() => setFlowSel(i)}>
              <span className="row vcenter gap8" style={{ minWidth: 0 }}>
                <span className="flow-idx">{i + 1}</span>
                <span style={{ fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{flowNodeLabel(node.label)}</span>
              </span>
              <Tag k={node.cap}>{capLabel(node.cap)}</Tag>
            </button>
            {i < data.nodes.length - 1 && <div className="edge flow" style={{ height: 26 }} />}
          </div>
        ))}
      </div>
    </div>
  );
}

export function FlowAside() {
  const { flowSel } = useApp();
  const traceId = useActiveTrace();
  const { data } = useTraceFlow(traceId ?? undefined);
  const n = data?.nodes[flowSel] ?? data?.nodes[0];

  return (
    <div className="col fill">
      <div className="pad14" style={{ borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3">节点详情</span>
      </div>
      <div className="col gap12 pad14 fill scroll">
        {!n && <span className="muted sm">选择一个节点查看详情。</span>}
        {n && (
          <>
            <div className={`node ${n.cap}`} style={{ alignSelf: 'flex-start', cursor: 'default' }}>
              <span>{flowNodeLabel(n.label)}</span><Dot k={n.cap} />
            </div>
            <div className="col gap6">
              {([['来源', nodeSourceLabel(n.source)], ['可见角色', n.readers], ['经由', flowNodeLabel(n.via)]] as [string, string][]).map(([k, v]) => (
                <div key={k} className="row between sm">
                  <span className="muted">{k}</span>
                  <span className="muted2" style={{ textAlign: 'right' }}>{v || '-'}</span>
                </div>
              ))}
            </div>
            <div className="divln" />
            <span className="eyebrow">能力图例</span>
            <div className="col gap6">
              {LEGEND.map(([k, l]) => <Sw key={k} c={`var(--cap-${k})`}>{l}</Sw>)}
            </div>
            <div className="divln" />
            <Note>解析结果会保留原始数据的可信级别，防止被误当成可信输入。</Note>
          </>
        )}
      </div>
    </div>
  );
}
