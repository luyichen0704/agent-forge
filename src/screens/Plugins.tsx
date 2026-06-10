import { Icon, Dot, Note, Tag } from '../components/kit';
import { useApp } from '../lib/appContext';
import { usePlugins } from '../features/plugins';

// treeSel mapping for plugins screen:
// 0 = all, 1 = Explorer, 2 = Executor, 3 = PolicyEngine, 4 = AuditSink, 5 = LLMAdapter
const TREE_IFACE: Record<number, string | null> = {
  0: null,
  1: 'Explorer',
  2: 'Executor',
  3: 'PolicyEngine',
  4: 'AuditSink',
  5: 'LLMAdapter',
};

export function PluginsMain() {
  const { plugSel, setPlugSel, treeSel, setTreeSel, toast } = useApp();
  const { data, isLoading } = usePlugins();

  if (isLoading) return <div className="pad16 muted sm">加载插件…</div>;
  const plugins = data?.items ?? [];

  const ifaceFilter = TREE_IFACE[treeSel] ?? null;
  const visible = ifaceFilter ? plugins.filter((p) => p.iface === ifaceFilter) : plugins;

  // Keep plugSel and treeSel in sync
  function handleSelect(id: string, iface: string) {
    setPlugSel(id);
    const treeIdx = Object.entries(TREE_IFACE).find(([, v]) => v === iface)?.[0];
    if (treeIdx) setTreeSel(Number(treeIdx));
  }

  return (
    <div className="pad16 col gap12 fill scroll">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }} data-tour="plugins-grid">
        {visible.map((p) => {
          const selected = p.id === plugSel;
          return (
            <div key={p.id} className="card pad12 col gap8"
              style={{ cursor: 'pointer', borderColor: selected ? 'var(--accent)' : 'var(--line)',
                       boxShadow: selected ? '0 0 0 1px var(--accent)' : 'none' }}
              onClick={() => handleSelect(p.id, p.iface)}>
              <div className="row vcenter gap8">
                <span style={{ width: 28, height: 28, borderRadius: 7, background: 'var(--fill)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Icon n={p.icon} s={15} c="var(--ink-2)" />
                </span>
                <div className="col fill">
                  <span className="b sm mono">{p.iface}</span>
                  <span className="xs muted">{p.sub}</span>
                </div>
                <span className="xs muted tnum">{p.impls.filter((i) => i.status === 'ok').length}/{p.impls.length}</span>
              </div>
              <div className="row gap6 wrap">
                {p.impls.map((im, idx) => (
                  <span key={idx} className="swatch"><Dot k={im.status === 'ok' ? 'ok' : im.status === 'wait' ? 'wait' : 'off'} />{im.name}</span>
                ))}
              </div>
            </div>
          );
        })}
        <div className="card pad12 col gap8 center" role="button" tabIndex={0}
          onClick={() => toast('打开接口实现向导（演示）', 'info')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toast('打开接口实现向导（演示）', 'info'); } }}
          style={{ borderStyle: 'dashed', background: 'var(--fill-2)', color: 'var(--ink-3)', cursor: 'pointer' }}>
          <Icon n="puzzle" s={22} />
          <span className="sm b">+ 注册新接口实现</span>
          <span className="xs muted" style={{ textAlign: 'center' }}>实现接口 → 注册 → 内核零改动</span>
        </div>
      </div>
    </div>
  );
}

export function PluginsAside() {
  const { plugSel, toast } = useApp();
  const { data } = usePlugins();
  const p = data?.items.find((x) => x.id === plugSel) ?? data?.items[0];
  if (!p) return <div className="pad14 muted sm">无插件</div>;

  return (
    <div className="col fill">
      <div className="pad14 row between vcenter" style={{ borderBottom: '1px solid var(--line-2)' }}>
        <span className="h3 mono">{p.iface}</span>
        <Tag k="trusted">稳定接口</Tag>
      </div>
      <div className="col gap10 pad14 fill scroll">
        <span className="eyebrow">接口定义 interface</span>
        <div className="code">{p.code}</div>
        <div className="divln" />
        <span className="eyebrow">已注册实现</span>
        {p.impls.map((im, idx) => (
          <div key={idx} className="row vcenter gap8 sm muted2">
            <Dot k={im.status === 'ok' ? 'ok' : im.status === 'wait' ? 'wait' : 'off'} />{im.name}
            <span className="fill" /><span className="xs muted mono">{im.version}</span>
          </div>
        ))}
        <button className="row vcenter gap8 sm muted" onClick={() => toast(`为 ${p.iface} 接入新实现（演示）`, 'info')}
          style={{ all: 'unset', cursor: 'pointer', display: 'flex', color: 'var(--ink-3)' }}>
          <Icon n="plus" s={13} />接入新实现
        </button>
        <div className="divln" />
        <Note>接口稳定不变 · 客户的库/权限/模型/日志都靠插件接入。</Note>
      </div>
    </div>
  );
}
