#!/usr/bin/env python3
"""agent-forge 可视化安装向导（零依赖，仅用 Python 标准库）。

用法:
    python3 installer/install.py        # 然后浏览器打开 http://127.0.0.1:8800

它会起一个本地网页，点击即可：检测环境 → 填写配置(含从网关拉取可用模型) →
一键安装(起 Postgres/Redis、装依赖、建表、初始化数据、设管理员密码、启动 API+Worker)
→ 健康检查 → 打开应用。所有步骤的实时日志都在网页上滚动显示。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ── paths ──
ROOT = Path(__file__).resolve().parent.parent          # repo root
SERVER = ROOT / "server"
ENV_FILE = SERVER / ".env"
RUN_DIR = ROOT / "installer" / ".run"
RUN_DIR.mkdir(parents=True, exist_ok=True)

UV = shutil.which("uv") or "uv"
DOCKER = shutil.which("docker") or "docker"
NPM = shutil.which("npm") or "npm"

# ── shared, thread-safe install log ──
_LOG: list[str] = []
_LOCK = threading.Lock()
_RUNNING = {"active": False, "step": ""}


def logln(msg: str) -> None:
    with _LOCK:
        _LOG.append(msg)


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> int:
    """Run a command, streaming stdout/stderr into the install log."""
    logln(f"$ {' '.join(cmd)}")
    try:
        p = subprocess.Popen(cmd, cwd=str(cwd or ROOT), env={**os.environ, **(env or {})},
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except FileNotFoundError as e:
        logln(f"  ! {e}")
        return 127
    assert p.stdout
    for line in p.stdout:
        logln("  " + line.rstrip())
    p.wait()
    logln(f"  → exit {p.returncode}")
    return p.returncode


# ── environment detection ──
def detect() -> dict:
    def ver(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout.strip().splitlines()[0]
        except Exception:
            return None
    return {
        "uv": ver([UV, "--version"]),
        "docker": ver([DOCKER, "--version"]),
        "npm": ver([NPM, "--version"]),
        "python": ver(["python3", "--version"]),
        "env_exists": ENV_FILE.exists(),
        "server_dir": str(SERVER),
        "env_file": str(ENV_FILE),
    }


def fetch_models(base_url: str, api_key: str) -> list[str]:
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    return sorted(m["id"] for m in data.get("data", []) if m.get("id"))


def write_env(cfg: dict) -> None:
    lines = [
        f"APP_ENV={cfg.get('app_env', 'dev')}",
        f"SECRET_KEY={cfg.get('secret_key') or 'dev-only-change-me'}",
        f"DATABASE_URL={cfg.get('database_url')}",
        f"SYNC_DATABASE_URL={cfg.get('sync_database_url')}",
        f"REDIS_URL={cfg.get('redis_url')}",
        f"LLM_BASE_URL={cfg.get('llm_base_url')}",
        f"LLM_API_KEY={cfg.get('llm_api_key')}",
        f"PLLM_MODEL={cfg.get('pllm_model')}",
        f"QLLM_MODEL={cfg.get('qllm_model')}",
        f"CORS_ORIGINS={cfg.get('cors_origins')}",
        f"DEMO_LOGIN={str(cfg.get('demo_login', True)).lower()}",
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logln(f"wrote {ENV_FILE}")


DEFAULTS = {
    "app_env": "dev",
    "database_url": "postgresql+asyncpg://agentforge:agentforge@localhost:5544/agentforge",
    "sync_database_url": "postgresql+psycopg://agentforge:agentforge@localhost:5544/agentforge",
    "redis_url": "redis://localhost:6390/0",
    "llm_base_url": "https://api.camel-hub.com/v1",
    "pllm_model": "claude-sonnet-4-5",
    "qllm_model": "claude-haiku-4-5",
    "cors_origins": "http://localhost:5173,http://localhost:4173",
    "demo_login": True,
}

# ── install steps ──
def step_compose():       return run([DOCKER, "compose", "up", "-d"], cwd=SERVER)
def step_uv_sync():       return run([UV, "sync"], cwd=SERVER)
def step_migrate():       return run([UV, "run", "alembic", "upgrade", "head"], cwd=SERVER)
def step_seed():          return run([UV, "run", "python", "-m", "app.seed"], cwd=SERVER)


def step_admin_pw(pw: str) -> int:
    code = (
        "import asyncio;from sqlalchemy import select;from app.db import SessionLocal;"
        "from app.models import User;from app.services.security import hash_password\n"
        "async def m():\n"
        " async with SessionLocal() as db:\n"
        "  u=(await db.execute(select(User).where(User.email=='admin@company.com'))).scalar_one()\n"
        f"  u.password_hash=hash_password({pw!r});await db.commit();print('admin password set')\n"
        "asyncio.run(m())"
    )
    return run([UV, "run", "python", "-c", code], cwd=SERVER)


def _spawn(name: str, cmd: list[str]) -> None:
    logfile = RUN_DIR / f"{name}.log"
    logln(f"starting {name}: {' '.join(cmd)} (log: {logfile})")
    f = open(logfile, "w")
    p = subprocess.Popen(cmd, cwd=str(SERVER), stdout=f, stderr=subprocess.STDOUT,
                         start_new_session=True, env={**os.environ})
    (RUN_DIR / f"{name}.pid").write_text(str(p.pid))


def step_start_services() -> int:
    _spawn("api", [UV, "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8099"])
    _spawn("worker", [UV, "run", "arq", "app.worker.WorkerSettings"])
    return 0


def step_health() -> int:
    import time
    for _ in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8099/api/v1/health", timeout=4) as r:
                if r.status == 200:
                    logln("health OK: " + r.read().decode())
                    return 0
        except Exception:
            time.sleep(1)
    logln("! API did not become healthy in time")
    return 1


def stop_services() -> None:
    import signal
    for name in ("api", "worker"):
        pf = RUN_DIR / f"{name}.pid"
        if pf.exists():
            try:
                os.killpg(os.getpgid(int(pf.read_text())), signal.SIGTERM)
                logln(f"stopped {name}")
            except Exception as e:
                logln(f"stop {name}: {e}")
            pf.unlink(missing_ok=True)


SEQUENCE = [
    ("启动 Postgres/Redis", step_compose),
    ("安装后端依赖 (uv sync)", step_uv_sync),
    ("建表 (alembic upgrade)", step_migrate),
    ("初始化数据 (seed)", step_seed),
    ("启动 API + Worker", step_start_services),
    ("健康检查", step_health),
]


def run_sequence(admin_pw: str | None) -> None:
    _RUNNING["active"] = True
    try:
        for label, fn in SEQUENCE:
            _RUNNING["step"] = label
            logln(f"\n=== {label} ===")
            if fn() != 0:
                logln(f"!! 步骤失败: {label} — 已停止")
                return
            if label.startswith("初始化数据") and admin_pw:
                _RUNNING["step"] = "设置管理员密码"
                logln("\n=== 设置管理员密码 ===")
                step_admin_pw(admin_pw)
        logln("\n✅ 安装完成。打开 http://localhost:5173 (前端 npm run dev) 或部署 dist。")
    finally:
        _RUNNING["active"] = False
        _RUNNING["step"] = ""


# ── HTTP handler ──
class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            return self._send(200, HTML.encode(), "text/html; charset=utf-8")
        if self.path == "/api/detect":
            return self._send(200, {"detect": detect(), "defaults": DEFAULTS})
        if self.path.startswith("/api/log"):
            since = 0
            if "since=" in self.path:
                try: since = int(self.path.split("since=")[1])
                except ValueError: since = 0
            with _LOCK:
                lines = _LOG[since:]
                total = len(_LOG)
            return self._send(200, {"lines": lines, "next": total, "running": _RUNNING})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._body()
        except Exception:
            body = {}
        if self.path == "/api/models":
            try:
                return self._send(200, {"models": fetch_models(body["base_url"], body["api_key"])})
            except Exception as e:
                return self._send(502, {"error": str(e)})
        if self.path == "/api/save-env":
            write_env({**DEFAULTS, **body})
            return self._send(200, {"ok": True, "env_file": str(ENV_FILE)})
        if self.path == "/api/install":
            if _RUNNING["active"]:
                return self._send(409, {"error": "already running"})
            write_env({**DEFAULTS, **body.get("config", {})})
            threading.Thread(target=run_sequence, args=(body.get("admin_password"),), daemon=True).start()
            return self._send(200, {"ok": True})
        if self.path == "/api/stop":
            stop_services()
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})


HTML = r"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>agent-forge 安装向导</title><style>
:root{--ac:#4f46e5;--bg:#0e0f13;--pa:#fff;--ln:#e4e6eb;--mut:#6a7079}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,"Segoe UI",sans-serif;background:#f4f5f8;color:#14161a}
.wrap{max-width:880px;margin:0 auto;padding:28px 20px 60px}
.logo{display:flex;align-items:center;gap:10px;font-weight:700;font-size:18px;margin-bottom:4px}
.mk{width:26px;height:26px;border-radius:7px;background:var(--ac);color:#fff;display:flex;align-items:center;justify-content:center}
.sub{color:var(--mut);margin-bottom:22px}
.card{background:var(--pa);border:1px solid var(--ln);border-radius:10px;padding:16px 18px;margin-bottom:16px}
.card h3{margin:0 0 12px;font-size:14px}
.row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px}
label{display:block;font-size:12px;color:var(--mut);margin-bottom:4px}
input,select{width:100%;padding:8px 10px;border:1px solid var(--ln);border-radius:7px;font:inherit}
.col{flex:1;min-width:220px}
button{font:inherit;font-weight:600;padding:9px 16px;border-radius:7px;border:1px solid var(--ln);background:#fff;cursor:pointer}
button.pri{background:var(--ac);border-color:var(--ac);color:#fff}
button:disabled{opacity:.5;cursor:not-allowed}
.det{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;font-size:12px}
.det div{padding:8px 10px;border:1px solid var(--ln);border-radius:7px}
.ok{color:#0e9f6e}.bad{color:#d23b30}
pre{background:#0f1117;color:#c9cdd6;border-radius:8px;padding:12px;height:280px;overflow:auto;font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap}
.bar{height:6px;background:#eef0f3;border-radius:4px;overflow:hidden;margin:8px 0}
.bar>i{display:block;height:100%;background:var(--ac);width:0;transition:width .4s}
small{color:var(--mut)}
</style></head><body><div class=wrap>
<div class=logo><span class=mk>◆</span> agent·forge 安装向导</div>
<div class=sub>一个脚本起网页，点几下把整套系统装好并启动。</div>

<div class=card><h3>1 · 环境检测</h3><div class=det id=det>检测中…</div></div>

<div class=card><h3>2 · 配置</h3>
 <div class=row>
  <div class=col><label>环境 APP_ENV</label><select id=app_env><option>dev</option><option>prod</option></select></div>
  <div class=col><label>CORS 源</label><input id=cors_origins></div>
 </div>
 <div class=row>
  <div class=col><label>LLM 网关 BASE_URL</label><input id=llm_base_url></div>
  <div class=col><label>LLM API Key</label><input id=llm_api_key placeholder="sk-..."></div>
 </div>
 <div class=row><div class=col><button onclick=loadModels()>拉取可用模型</button> <small id=mstat></small></div></div>
 <div class=row>
  <div class=col><label>P-LLM 模型</label><select id=pllm_model></select></div>
  <div class=col><label>Q-LLM 模型</label><select id=qllm_model></select></div>
 </div>
 <div class=row>
  <div class=col><label>数据库 DATABASE_URL</label><input id=database_url></div>
 </div>
 <div class=row>
  <div class=col><label>管理员密码 (admin@company.com)</label><input id=admin_password type=password placeholder="安装后用它登录"></div>
 </div>
</div>

<div class=card><h3>3 · 一键安装</h3>
 <button class=pri id=go onclick=install()>开始安装</button>
 <button onclick=stop()>停止服务</button>
 <div class=bar><i id=prog></i></div>
 <small id=step></small>
 <pre id=log>（日志将在这里实时滚动）</pre>
</div>

<div class=card id=done style=display:none><h3>4 · 完成</h3>
 <p>API 健康检查通过。后端: <code>http://127.0.0.1:8099</code> · 文档 <code>/docs</code></p>
 <p>前端开发预览：在仓库根执行 <code>npm install &amp;&amp; npm run dev</code> → <a href=http://localhost:5173 target=_blank>http://localhost:5173</a></p>
 <p>用 <b>admin@company.com</b> + 你设置的密码登录（生产需把 APP_ENV=prod、DEMO_LOGIN 会自动关）。</p>
</div>

<script>
const $=id=>document.getElementById(id);
let D={};
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function boot(){
 const r=await j('/api/detect');D=r.defaults;const d=r.detect;
 const row=(k,v,ok)=>`<div><b>${k}</b><br><span class=${ok?'ok':'bad'}>${v||'未安装'}</span></div>`;
 $('det').innerHTML=row('uv',d.uv,d.uv)+row('docker',d.docker,d.docker)+row('npm',d.npm,d.npm)+row('python',d.python,d.python)+row('server',d.server_dir,1);
 for(const k of ['app_env','cors_origins','llm_base_url','database_url','pllm_model','qllm_model']) if($(k)) $(k).value=D[k]||'';
}
async function loadModels(){
 $('mstat').textContent='拉取中…';
 const r=await j('/api/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_url:$('llm_base_url').value,api_key:$('llm_api_key').value})});
 if(r.error){$('mstat').textContent='失败: '+r.error;return}
 for(const sel of ['pllm_model','qllm_model']){const cur=$(sel).value;$(sel).innerHTML=r.models.map(m=>`<option ${m===cur?'selected':''}>${m}</option>`).join('')}
 $('mstat').textContent=`共 ${r.models.length} 个模型`;
}
function cfg(){return {app_env:$('app_env').value,cors_origins:$('cors_origins').value,llm_base_url:$('llm_base_url').value,llm_api_key:$('llm_api_key').value,pllm_model:$('pllm_model').value,qllm_model:$('qllm_model').value,database_url:$('database_url').value,demo_login:$('app_env').value!=='prod'}}
let since=0,poll=null;
async function install(){
 $('go').disabled=true;$('log').textContent='';since=0;
 await j('/api/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:cfg(),admin_password:$('admin_password').value})});
 poll=setInterval(tick,800);
}
async function tick(){
 const r=await j('/api/log?since='+since);since=r.next;
 if(r.lines.length){$('log').textContent+=r.lines.join('\n')+'\n';$('log').scrollTop=$('log').scrollHeight}
 $('step').textContent=r.running.step||'';
 const steps=6,idx=['启动 Postgres','安装后端','建表','初始化','启动 API','健康'].findIndex(s=>(r.running.step||'').includes(s));
 $('prog').style.width=(r.running.active?Math.max(5,(idx+1)/steps*100):($('log').textContent.includes('安装完成')?100:0))+'%';
 if(!r.running.active&&$('log').textContent.includes('健康 OK')||$('log').textContent.includes('health OK')){clearInterval(poll);$('go').disabled=false;$('done').style.display='block'}
 if(!r.running.active&&since>0&&$('log').textContent.includes('exit')){$('go').disabled=false}
}
async function stop(){await j('/api/stop',{method:'POST'});}
boot();
</script></div></body></html>"""


def main() -> None:
    port = int(os.getenv("INSTALLER_PORT", "8800"))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{port}"
    print(f"\n  agent-forge 安装向导 → {url}\n  (Ctrl-C 退出)\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
