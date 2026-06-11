import { useState, useSyncExternalStore } from 'react';
import { getToken, subscribeToken } from './api/http';
import { useMe, login, passwordLogin } from './features/auth';
import { Shell } from './components/Shell';
import { Icon } from './components/kit';
import type { Role } from './api/types';

const ROLE_LABELS: Array<[Role, string]> = [
  ['admin', '管理员'], ['employee', '员工'], ['customer', '客户'],
];

function Login() {
  const [email, setEmail] = useState('admin@company.com');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      await passwordLogin(email.trim(), password);
    } catch (e2) {
      setErr((e2 as Error).message || '登录失败');
    } finally {
      setBusy(false);
    }
  }

  async function devLogin(r: Role) {
    setErr(null);
    try {
      await login(r);
    } catch (e2) {
      setErr('演示登录已禁用（生产环境请用账号密码）');
    }
  }

  return (
    <div className="wf center" style={{ background: 'var(--canvas)' }}>
      <div className="card pad16 col gap12" style={{ width: 340 }}>
        <div className="logo" style={{ fontSize: 16 }}>
          <span className="mk"><Icon n="hex" s={15} c="#fff" /></span>
          <span>agent<span style={{ color: 'var(--accent)' }}>·</span>forge</span>
        </div>
        <span className="sm muted">企业 AI Agent 治理控制台</span>

        <form className="col gap8" onSubmit={submit}>
          <label className="field"><Icon n="user" s={14} c="var(--ink-4)" />
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="邮箱" aria-label="邮箱" />
          </label>
          <label className="field"><Icon n="lock" s={14} c="var(--ink-4)" />
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder="密码" aria-label="密码" />
          </label>
          <button className="btn pri lg" type="submit" disabled={busy || !password}>
            {busy ? '登录中…' : '登录'}
          </button>
        </form>

        {err && <span className="sm" style={{ color: 'var(--danger)' }}>{err}</span>}

        <div className="divln" />
        <span className="eyebrow">开发演示 · 免密角色登录</span>
        <div className="row gap6">
          {ROLE_LABELS.map(([r, label]) => (
            <button key={r} className="btn sm fill" onClick={() => devLogin(r)}>{label}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const hasToken = !!useSyncExternalStore(subscribeToken, getToken);
  const me = useMe();

  if (!hasToken) return <Login />;
  if (me.isLoading) return <div className="wf center muted sm">加载中…</div>;
  if (me.isError || !me.data) return <Login />;
  return <Shell />;
}
