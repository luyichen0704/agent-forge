import { Icon, Btn, Tag, Dot, Note } from '../components/kit';
import { DATA_SOURCES, EXPLORE_PHASES } from '../lib/data';

/* ---- ExploreMain: 数据源管理 + 5 source cards ---- */
export function ExploreMain() {
  return (
    <div className="col fill">
      {/* topbar */}
      <div
        className="row between vcenter"
        style={{
          padding: '14px 18px',
          borderBottom: '1px solid var(--line)',
          background: 'var(--paper)',
        }}
      >
        <div className="col">
          <span className="h2">数据源管理</span>
          <span className="sm muted">挂载企业系统 · 自主探索生成 Operation Registry</span>
        </div>
        <div className="row gap8">
          <Btn ic="refresh">增量更新</Btn>
          <Btn k="pri" ic="play">开始探索</Btn>
        </div>
      </div>

      {/* source list */}
      <div className="col gap10 fill" style={{ padding: 16, overflowY: 'auto' }}>
        {DATA_SOURCES.map((s, i) => (
          <div key={i} className="card row vcenter gap12" style={{ padding: 12 }}>
            {/* icon box */}
            <span
              style={{
                width: 34,
                height: 34,
                borderRadius: 8,
                background: 'var(--fill)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <Icon n={s.icon} s={18} c="var(--ink-2)" />
            </span>

            {/* label + conn */}
            <div className="col" style={{ width: 150 }}>
              <span className="b sm">{s.label}</span>
              <span className="xs muted mono">{s.conn}</span>
            </div>

            {/* progress bar (only for crawling source) */}
            <div className="fill">
              {s.dotKind === 'wait' && s.progress != null && (
                <div className="prog" style={{ maxWidth: 220 }}>
                  <i style={{ width: `${s.progress}%` }} />
                </div>
              )}
            </div>

            {/* status label */}
            <div className="row vcenter gap6 sm muted2">
              <Dot k={s.dotKind} />
              {s.statusLabel}
            </div>

            <Icon n="dots" s={16} c="var(--ink-4)" />
          </div>
        ))}

        {/* add new explorer card */}
        <div
          className="card row vcenter gap12"
          style={{
            padding: 12,
            borderStyle: 'dashed',
            background: 'var(--fill-2)',
          }}
        >
          <span
            style={{
              width: 34,
              height: 34,
              borderRadius: 8,
              background: 'var(--accent-soft)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Icon n="puzzle" s={18} c="#9c4a2e" />
          </span>
          <div className="col fill">
            <span className="b sm">+ 接入新探索器 Explorer 插件</span>
            <span className="xs muted">
              实现 Explorer 接口即可挂载任意数据源（gRPC、消息队列、SaaS…）
            </span>
          </div>
          <Btn sz="sm" ic="plus">
            添加
          </Btn>
        </div>
      </div>
    </div>
  );
}

/* ---- ExploreAside: CodeExplorer panel ---- */
export function ExploreAside() {
  return (
    <div className="col fill">
      {/* header */}
      <div
        className="row between vcenter"
        style={{
          padding: '12px 14px',
          borderBottom: '1px solid var(--line-2)',
        }}
      >
        <span className="h3">CodeExplorer</span>
        <Tag k="trusted">active</Tag>
      </div>

      {/* body */}
      <div className="col gap10 fill" style={{ padding: 14, overflowY: 'auto' }}>
        {/* connector */}
        <div className="col gap6">
          <span className="eyebrow">连接 Connector</span>
          <div className="field" style={{ gap: 0 }}>
            <span className="mono xs">git@github.com:company/backend</span>
          </div>
        </div>

        {/* explore phases */}
        <div className="col gap6">
          <span className="eyebrow">探索阶段 Phases</span>
          {EXPLORE_PHASES.map((p, i) => (
            <div key={i} className="row vcenter gap8 sm muted2">
              <Dot k={p.state === 'done' ? 'ok' : p.state === 'now' ? 'wait' : 'off'} />
              {`① ② ③ ④`.split(' ')[i]} {p.sub}
            </div>
          ))}
        </div>

        <div className="divln" />

        {/* interface signature */}
        <span className="eyebrow">实现接口 implements</span>
        <div className="code">
          {'class Explorer(ABC):\n  async def '}
          <span className="f">explore</span>
          {'(self,\n    src) -> list['}
          <span className="v">OperationDraft</span>
          {']'}
        </div>

        <Note style={{ marginTop: 2 }}>↳ 换数据源 = 新写一个 Explorer 即可</Note>
      </div>
    </div>
  );
}
