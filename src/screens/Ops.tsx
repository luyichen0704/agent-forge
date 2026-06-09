import { Icon, Btn, Chip, Tag, Dot, Note } from '../components/kit';
import { useApp } from '../lib/appContext';
import type { Operation } from '../lib/types';

/* treeSel → row filter */
function matchTree(o: Operation, treeSel: number): boolean {
  switch (treeSel) {
    case 1: return o.status === 'pending';
    case 2: return o.type === 'q' && o.status === 'active';
    case 3: return o.type === 'm';
    case 4: return o.status === ('disabled' as Operation['status']); // none in demo
    default: return true;
  }
}

export function OpsMain() {
  const { role, ops, opsSel, setOpsSel, treeSel, query } = useApp();
  const readonly = role !== 'admin';

  const visible = ops
    .filter(o => o.roles.includes(role))
    .filter(o => matchTree(o, treeSel))
    .filter(o => !query || o.name.toLowerCase().includes(query.toLowerCase()));

  const stColor = (s: string) => (s === 'active' ? 'var(--cap-trusted)' : 'var(--cap-write)');

  return (
    <div className="pad16 fill scroll">
      {readonly && (
        <div className="row vcenter gap6 sm muted" style={{ marginBottom: 10 }}>
          <Icon n="eye" s={14} c="var(--ink-3)" />
          {role} 视角 · 只显示你可调用的操作 · 审核为只读
        </div>
      )}
      <div className="card" style={{ overflow: 'hidden' }}>
        <table className="tbl">
          <thead>
            <tr style={{ cursor: 'default' }}>
              <th>操作</th><th>类型</th><th>权限</th><th>确认级别</th><th>状态</th><th></th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr style={{ cursor: 'default' }}>
                <td colSpan={6} className="muted sm" style={{ padding: '16px 12px', textAlign: 'center' }}>
                  无匹配操作
                </td>
              </tr>
            )}
            {visible.map(o => (
              <tr key={o.name} className={o.name === opsSel ? 'sel' : ''} onClick={() => setOpsSel(o.name)}>
                <td className="mono b" style={{ color: 'var(--ink)' }}>{o.name}</td>
                <td><Tag k={o.type}>{o.type === 'm' ? 'mutation' : 'query'}</Tag></td>
                <td className="mono">{o.perm}</td>
                <td>
                  {o.confirm === 'dual'
                    ? <span style={{ color: 'var(--danger)' }} className="b">dual_approval</span>
                    : o.confirm}
                </td>
                <td>
                  <span className="row vcenter gap5">
                    <Dot k={o.status === 'active' ? 'ok' : 'wait'} />
                    <span style={{ color: stColor(o.status) }}>{o.status}</span>
                  </span>
                </td>
                <td><Icon n="dots" s={15} c="var(--ink-4)" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {role === 'admin' && (
        <div className="col gap8" style={{ marginTop: 14 }}>
          <span className="eyebrow">可插拔后端 · 高扩展性</span>
          <div className="row gap8 wrap">
            <Chip ic="puzzle">Policy: Python · OPA · Casbin</Chip>
            <Chip ic="bolt">Executor: API · Function · SQL · RPA</Chip>
            <Chip ic="plus">注册插件</Chip>
          </div>
        </div>
      )}
    </div>
  );
}

export function OpsAside() {
  const { role, ops, opsSel, setOpStatus, toast } = useApp();
  const visible = ops.filter(o => o.roles.includes(role));
  const o = visible.find(x => x.name === opsSel) || visible[0];

  if (!o) return <div className="pad14 muted sm">无可见操作</div>;

  const isM = o.type === 'm';

  /* dual_approval panel — admin only */
  if (o.confirm === 'dual') {
    return (
      <div className="col pad14 fill gap10 scroll">
        <div className="row between vcenter">
          <span className="h3 mono">{o.name}</span>
          <Tag k="write">dual approval</Tag>
        </div>
        <div className="card pad12 col gap8" style={{ borderColor: 'var(--cap-write)', background: 'var(--cap-write-bg)' }}>
          <span className="eyebrow" style={{ color: '#a8480a' }}>待双人确认 · 高风险写操作</span>
          <div className="row between sm"><span style={{ color: '#a8480a' }}>发起人</span><span className="mono muted2">hr.li@company</span></div>
          <div className="row between sm"><span style={{ color: '#a8480a' }}>对象</span><span className="mono muted2">员工 #2031</span></div>
        </div>
        <span className="eyebrow">改动 diff</span>
        <div className="code">
          {'salary:\n  '}<span className="c">- ¥28,000</span>{'\n  '}<span className="s">+ ¥32,000</span>
        </div>
        <div className="divln" />
        <span className="eyebrow">确认链</span>
        <div className="row vcenter gap8 sm">
          <Icon n="check" s={14} c="var(--cap-trusted)" /><span className="muted2">mgr.zhao 已批准</span><span className="xs muted">12:01</span>
        </div>
        <div className="row vcenter gap8 sm"><Dot k="wait" /><span className="muted2">等待第二管理员(你)</span></div>
        <div className="row gap8" style={{ marginTop: 4 }}>
          <Btn sz="sm" k="go" ic="check" onClick={() => { setOpStatus(o.name, 'active'); toast('已确认执行 · 已入审计链'); }}>确认执行</Btn>
          <Btn sz="sm" k="warn" ic="x" onClick={() => toast('已拒绝该操作', 'warn')}>拒绝</Btn>
        </div>
        <Note>两名管理员都确认后才执行，全程入审计链。</Note>
      </div>
    );
  }

  /* default op detail panel */
  return (
    <div className="col pad14 fill gap10 scroll">
      <div className="row between vcenter">
        <span className="h3 mono">{o.name}</span>
        <Tag k={o.type}>{isM ? 'mutation' : 'query'}</Tag>
      </div>
      {([
        ['语义', isM ? '执行一次写操作' : '查询数据'],
        ['参数', '见 Registry schema'],
        ['权限', o.perm],
        ['确认级别', o.confirm],
        ['执行', 'API · Function · SQL fallback'],
      ] as [string, string][]).map(([k, v], i) => (
        <div key={i} className="row gap8 sm">
          <span className="muted" style={{ width: 52, flex: '0 0 auto' }}>{k}</span>
          <span className="muted2">{v}</span>
        </div>
      ))}
      <div className="divln" />
      <div className="row between vcenter">
        <span className="eyebrow">关联策略 policy</span>
        <Chip ic="puzzle">PythonPolicyEngine</Chip>
      </div>
      <div className="code">
        {'def '}<span className="f">{o.name.replace('.', '_')}_policy</span>{'(id, op, kw):\n  '}
        <span className="k">if</span>{' src ⊄ trusted:\n    '}<span className="k">return</span>{' Denied(...)'}
      </div>
      {role === 'admin'
        ? (o.status === 'pending'
          ? (
            <div className="row gap8" style={{ marginTop: 2 }}>
              <Btn sz="sm" k="go" ic="check" onClick={() => { setOpStatus(o.name, 'active'); toast(`已批准 ${o.name}`); }}>批准激活</Btn>
              <Btn sz="sm" ic="sliders" onClick={() => toast('打开参数调整（演示）', 'info')}>调整</Btn>
              <Btn sz="sm" k="ghost" onClick={() => toast(`已禁用 ${o.name}`, 'warn')}>禁用</Btn>
            </div>
          )
          : (
            <div className="row vcenter gap6 sm" style={{ color: 'var(--cap-trusted)', marginTop: 2 }}>
              <Icon n="check" s={14} c="var(--cap-trusted)" />已激活 · {o.type === 'q' ? 'query 自动上线' : '写操作已审核'}
            </div>
          ))
        : (
          <div className="row vcenter gap6 sm muted" style={{ marginTop: 2 }}>
            <Icon n="eye" s={14} c="var(--ink-3)" />只读 · 审核需管理员
          </div>
        )}
    </div>
  );
}
