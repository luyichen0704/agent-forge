import { FLOW_NODES } from '../lib/data';
import { Dot, Note, Sw } from '../components/kit';

/* capability legend entries */
const LEGEND: Array<[string, string]> = [
  ['trusted', '🟢 可信 user'],
  ['data',    '🔵 内部数据'],
  ['parsed',  '🟡 解析结果'],
  ['write',   '🟠 写操作'  ],
];

/* ---- FlowMain ---- */
export function FlowMain() {
  return (
    <div className="fill center" style={{ background: 'var(--fill-2)' }}>
      <div className="col center gap8">
        {FLOW_NODES.map((node, i) => (
          <div key={i}>
            {/* node */}
            <div
              className={`node ${node.cap}`}
              style={{ width: 320, justifyContent: 'space-between' }}
            >
              <span className="mono" style={{ fontSize: 11 }}>{node.label}</span>
              <Dot k={node.cap} />
            </div>
            {/* edge connector between nodes */}
            {i < FLOW_NODES.length - 1 && (
              <div className="edge" style={{ height: 16 }} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---- FlowAside ---- */
export function FlowAside() {
  return (
    <div className="col fill">
      {/* header */}
      <div
        className="pad14"
        style={{ borderBottom: '1px solid var(--line-2)' }}
      >
        <span className="h3">节点详情 · node</span>
      </div>

      <div className="col gap10 pad14 fill">
        {/* highlighted node: refund_orders (parsed) */}
        <div className="node parsed" style={{ alignSelf: 'flex-start' }}>
          refund_orders
        </div>

        {/* node detail rows */}
        <div className="col gap6">
          <div className="row between sm">
            <span className="muted">source</span>
            <span className="mono muted2">database.orders</span>
          </div>
          <div className="row between sm">
            <span className="muted">readers</span>
            <span className="mono muted2">emp, admin</span>
          </div>
          <div className="row between sm">
            <span className="muted">via</span>
            <span className="mono muted2">Q-LLM (无放宽)</span>
          </div>
        </div>

        <div className="divln" />

        {/* capability legend */}
        <div className="col gap6">
          {LEGEND.map(([k, l], i) => (
            <Sw key={i} c={`var(--cap-${k})`}>{l}</Sw>
          ))}
        </div>

        <div className="divln" />

        {/* explanatory note */}
        <Note>Q-LLM 输出继承输入能力 → 防数据洗白</Note>
      </div>
    </div>
  );
}
