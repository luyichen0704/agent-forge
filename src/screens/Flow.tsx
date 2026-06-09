import { FLOW_NODES } from '../lib/data';
import { Dot, Note, Sw } from '../components/kit';
import { useApp } from '../lib/appContext';
import type { CapKind } from '../lib/types';

/* capability legend entries */
const LEGEND: Array<[CapKind, string]> = [
  ['trusted', '可信 · user 直接输入'],
  ['data',    '内部数据 · 库直读'],
  ['parsed',  '解析结果 · Q-LLM'],
  ['write',   '写操作 · 副作用'],
];

/* ---- FlowMain ---- */
export function FlowMain() {
  const { flowSel, setFlowSel } = useApp();

  return (
    <div className="fill center scroll" style={{ background: 'var(--canvas)', padding: 24 }}>
      <div className="col center gap2">
        {FLOW_NODES.map((node, i) => (
          <div key={i} className="col center">
            <button
              className={`node ${node.cap} ${i === flowSel ? 'sel' : ''}`}
              style={{ width: 320, justifyContent: 'space-between' }}
              onClick={() => setFlowSel(i)}
            >
              <span className="mono" style={{ fontSize: 11 }}>{node.label}</span>
              <Dot k={node.cap} />
            </button>
            {i < FLOW_NODES.length - 1 && <div className="edge flow" style={{ height: 26 }} />}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---- FlowAside ---- */
export function FlowAside() {
  const { flowSel } = useApp();
  const n = FLOW_NODES[flowSel] ?? FLOW_NODES[3];

  return (
    <div className="col fill">
      <div className="pad14" style={{ borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3">节点详情 · node</span>
      </div>

      <div className="col gap12 pad14 fill scroll">
        <div className={`node ${n.cap}`} style={{ alignSelf: 'flex-start', cursor: 'default' }}>
          <span className="mono">{n.node}</span>
          <Dot k={n.cap} />
        </div>

        <div className="col gap6">
          {([['source', n.source], ['readers', n.readers], ['via', n.via]] as [string, string][]).map(([k, v]) => (
            <div key={k} className="row between sm">
              <span className="muted">{k}</span>
              <span className="mono muted2" style={{ textAlign: 'right' }}>{v}</span>
            </div>
          ))}
        </div>

        <div className="divln" />

        <span className="eyebrow">能力图例 capabilities</span>
        <div className="col gap6">
          {LEGEND.map(([k, l]) => (
            <Sw key={k} c={`var(--cap-${k})`}>{l}</Sw>
          ))}
        </div>

        <div className="divln" />

        <Note>Q-LLM 输出继承输入能力，防止数据被「洗白」成可信。</Note>
      </div>
    </div>
  );
}
