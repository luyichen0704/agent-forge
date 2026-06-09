# agent-forge 生产部署运行手册

本手册把 agent-forge 从 demo 切换为**生产**：真实密码登录（关闭 demo role-login）、强配置校验、结构化日志、反向代理 + TLS、专用服务账号与最小权限。提供 **A. 单机 systemd** 与 **B. 容器 (docker compose)** 两套可直接照做的方案。

> 三块强制信息分别在 §6（日志位置）、§7（工作目录路径）、§8（访问与操作权限）集中列出。

---

## 1. 应用是怎么做的（架构与组成）

```
浏览器 ──HTTPS──> nginx (TLS 终止, 443)
                   ├── /            → 静态 SPA (Vite 构建产物 dist)
                   └── /api/, SSE   → 反代 127.0.0.1:8099
                                       agent-forge API (gunicorn + uvicorn worker)
                                         ├── PostgreSQL  (业务/审计/注册表/会话)
                                         ├── Redis       (SSE/事件总线)
                                         └── camel-hub   (OpenAI 兼容 LLM 网关, P-LLM/Q-LLM)
```

- **后端** `server/`：FastAPI + async SQLAlchemy2 + Alembic，6 个限界上下文（identity / sources / registry / chat-plans / executions-approvals / audit-traces）+ CaMeL 引擎（planner=P-LLM、qparser=Q-LLM、能力格、策略引擎、可插拔执行器、审计哈希链）。用 `uv` 管依赖。
- **前端** `src/`：React18 + TS + Vite + react-query；登录拿 token，后续请求带 `Authorization: Bearer`；构建产物是纯静态文件。
- **进程**：API 由 `gunicorn -c gunicorn.conf.py app.main:app`（uvicorn worker）跑，仅监听 `127.0.0.1:8099`，由 nginx 终止 TLS 并反代。

---

## 2. 模型配置与所有"细节"保存在哪、怎么保存

分两层，**密钥/模型在环境变量，运营数据在数据库**：

### 2.1 模型 / LLM / 密钥 = 环境变量（不进 git、不进镜像、不进 DB）
定义于 `server/app/config.py` 的 `Settings`，从环境/`.env` 读取：

| 项 | 环境变量 | 默认 | 消费点 |
|---|---|---|---|
| P-LLM 模型 | `PLLM_MODEL` | `claude-sonnet-4-5` | `services/planner.py`、`explorer.py`、`api/health.py` |
| Q-LLM 模型 | `QLLM_MODEL` | `claude-haiku-4-5` | `services/qparser.py`、`api/health.py` |
| LLM 网关 | `LLM_BASE_URL` | `https://api.camel-hub.com/v1` | `services/llm.py` |
| **LLM 密钥** | `LLM_API_KEY` | （空，必填） | `services/llm.py` |
| 会话密钥 | `SECRET_KEY` | `dev-only`（生产必改 ≥32 随机） | 会话/签名 |
| DB | `DATABASE_URL`/`SYNC_DATABASE_URL` | dev 默认 | `db.py`、`alembic/env.py` |

**生产存放方式**：写入 `/etc/agent-forge/server.env`，`chown root:agentforge && chmod 0640`（只有服务用户可读），由 systemd `EnvironmentFile=` 注入；容器方案用 compose `env_file:` / Docker secret。模板见 `deploy/env/server.env.prod.example`。`APP_ENV=prod` 时 `Settings.validate_production()` 会在启动时**拒绝**弱 `SECRET_KEY`、缺 `LLM_API_KEY`、`CORS` 含 `*`、默认 DB 密码、`DEMO_LOGIN=true` 等不安全配置（`app/main.py` lifespan 触发）。

### 2.2 运营数据 = PostgreSQL（由 app/界面管理，`app/seed.py` 初始化）
`operations`/`operation_permissions`（操作注册表+ABAC 权限）、`plugins`/`plugin_registrations`、`data_sources`、`roles`/`users`/`user_roles`、`sessions`、`traces`/`audit_events`/`executions`/`dataflow_*`/`llm_runs`、`biz_records`。这些不是配置文件，是数据库行，随 DB 备份一起持久化（§9）。

### 2.3 密钥轮换 / 热加载
- **轮换 `LLM_API_KEY`/`SECRET_KEY`**：改 `/etc/agent-forge/server.env` → `sudo systemctl reload-or-restart agent-forge-api`（gunicorn 优雅重启，旧 worker 处理完在途请求再退出，见 `gunicorn.conf.py graceful_timeout`）。会话存在 DB，重启不丢登录。
- **换模型**（`PLLM_MODEL`/`QLLM_MODEL`）：同上改 env + reload。换前用 `GET /api/v1/health/llm` 验证目标模型在网关可用。
- **建议（roadmap，未实现）**：把"每租户可切换模型/温度/超时"下沉一张 `llm_profiles(tenant_id, role, model, temperature, timeout)` 表，env 只留密钥与默认 profile —— 换模型无需改 env/重启。

---

## 3. 前置准备

- 一台 Linux 主机（Debian/Ubuntu 示例），具备 sudo。
- 域名解析到主机，开放 80/443。
- 已有或将部署 PostgreSQL 16 与 Redis 7。
- camel-hub 的 `LLM_API_KEY`。

```bash
# 安装基础组件（systemd 方案）
sudo apt update && sudo apt install -y nginx postgresql redis-server certbot python3-certbot-nginx git
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh   # uv
# Node 22（构建前端用，构建机即可，不必装在生产主机）
```

---

## 4. 方案 A：单机 systemd（推荐用于自管主机）

```bash
# 4.1 专用服务用户（无登录 shell）
sudo useradd --system --create-home --home-dir /opt/agent-forge --shell /usr/sbin/nologin agentforge

# 4.2 拉代码到安装根目录
sudo -u agentforge git clone https://github.com/kuangren777/agent-forge /opt/agent-forge
cd /opt/agent-forge

# 4.3 后端依赖（生产不装 dev 组）
sudo -u agentforge bash -lc 'cd /opt/agent-forge/server && uv sync --no-dev'

# 4.4 数据库角色与库（最小权限，非超级用户）
sudo -u postgres psql <<'SQL'
CREATE ROLE agentforge LOGIN PASSWORD '强随机密码';
CREATE DATABASE agentforge OWNER agentforge;
SQL

# 4.5 配置文件（密钥）
sudo mkdir -p /etc/agent-forge
sudo cp deploy/env/server.env.prod.example /etc/agent-forge/server.env
sudo nano /etc/agent-forge/server.env          # 填 SECRET_KEY / DATABASE_URL / LLM_API_KEY / CORS_ORIGINS
sudo chown root:agentforge /etc/agent-forge/server.env && sudo chmod 0640 /etc/agent-forge/server.env

# 4.6 日志目录
sudo mkdir -p /var/log/agent-forge
sudo chown agentforge:agentforge /var/log/agent-forge && sudo chmod 0750 /var/log/agent-forge

# 4.7 建表 + 首次初始化数据（迁移用 SYNC_DATABASE_URL）
sudo -u agentforge bash -lc 'cd /opt/agent-forge/server && set -a && . /etc/agent-forge/server.env && set +a && uv run alembic upgrade head && uv run python -m app.seed'

# 4.8 安装并启动 systemd 服务
sudo cp deploy/systemd/agent-forge-api.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now agent-forge-api
curl -s http://127.0.0.1:8099/api/v1/health         # {"status":"ok","env":"prod"}

# 4.9 前端构建并部署为静态文件（可在构建机上 build 后 rsync 过来）
npm ci && npm run build
sudo mkdir -p /opt/agent-forge/web && sudo cp -r dist/* /opt/agent-forge/web/
sudo chown -R agentforge:agentforge /opt/agent-forge/web

# 4.10 nginx + TLS
sudo cp deploy/nginx/agent-forge.conf /etc/nginx/sites-available/agent-forge.conf
sudo ln -sf /etc/nginx/sites-available/agent-forge.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d agent-forge.example.com     # 签发并自动续期
```

创建**真实管理员**（关闭 demo 后用密码登录）：

```bash
sudo -u agentforge bash -lc 'cd /opt/agent-forge/server && set -a && . /etc/agent-forge/server.env && set +a && uv run python - <<PY
import asyncio
from app.db import SessionLocal
from app.services.security import hash_password
from sqlalchemy import select
from app.models import User
async def m():
    async with SessionLocal() as db:
        u=(await db.execute(select(User).where(User.email=="admin@company.com"))).scalar_one()
        u.password_hash=hash_password("在这里设强密码"); await db.commit(); print("password set")
asyncio.run(m())
PY'
```
登录走 `POST /api/v1/auth/token {email,password}`（demo 的 `/auth/login` 在 prod 返回 403）。

---

## 5. 方案 B：容器（docker compose）

```bash
git clone https://github.com/kuangren777/agent-forge && cd agent-forge
cp deploy/env/server.env.prod.example deploy/env/server.env
nano deploy/env/server.env                         # 同上填值；DATABASE_URL 用 db 主机名
chmod 0640 deploy/env/server.env
export POSTGRES_PASSWORD='强随机密码'                # 供 compose 的 db 服务
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
docker compose -f docker-compose.prod.yml exec api python -m app.seed   # 仅首次
# web 暴露在 127.0.0.1:8080，前面再挂一层 TLS 边缘代理/负载均衡
```

升级：`git pull && docker compose -f docker-compose.prod.yml up -d --build && docker compose ... exec api alembic upgrade head`。

---

## 6. 【运行日志与详细日志的存放位置】

| 来源 | 位置 | 说明 / 查看 |
|---|---|---|
| **应用结构化日志** | `/var/log/agent-forge/app.log` | `LOG_DIR` 控制；`RotatingFileHandler` 20MB×10 份（`app.log.1..10`）；`LOG_JSON=true` 为一行 JSON；含每请求 access 行（method/path/status/latency/request_id） |
| **API stdout/stderr** | systemd journald | `journalctl -u agent-forge-api -f`（`-n 200`、`--since today`）；容器：`docker compose -f docker-compose.prod.yml logs -f api` |
| **gunicorn access/error** | 默认 stdout（→ journald/app.log）；可设 `GUNICORN_ACCESS_LOG`/`GUNICORN_ERROR_LOG` 为文件路径 | `server/gunicorn.conf.py` |
| **nginx 访问/错误** | `/var/log/nginx/agent-forge.access.log`、`/var/log/nginx/agent-forge.error.log` | 见 `deploy/nginx/agent-forge.conf` |
| **PostgreSQL** | `/var/log/postgresql/postgresql-16-main.log`（apt 默认）；容器在 `docker logs` | 慢查询/错误 |
| **Redis** | `/var/log/redis/redis-server.log`（apt 默认） | |
| **LLM 调用审计** | **数据库** `llm_runs` 表（trace_id/role/model/token_usage/latency） | 业务级可追溯，不只在文本日志 |
| **审计链** | **数据库** `audit_events`（哈希链，`GET /api/v1/traces/:id/audit` 可验证完整性） | |

**日志级别**：`LOG_LEVEL`（默认 INFO）。**轮转**：app.log 由 Python 自身轮转；journald 用系统配置（`/etc/systemd/journald.conf` 的 `SystemMaxUse`）；nginx 由 `/etc/logrotate.d/nginx`。

---

## 7. 【文件工作目录的具体路径】

| 用途 | systemd 方案绝对路径 | 容器方案 |
|---|---|---|
| 应用安装根目录 | `/opt/agent-forge` | 镜像内 `/app`（后端） |
| 后端代码 / 工作目录 | `/opt/agent-forge/server`（systemd `WorkingDirectory`） | `/app` |
| Python 虚拟环境 | `/opt/agent-forge/server/.venv` | 镜像内 `/app/.venv` |
| 环境/密钥文件 | `/etc/agent-forge/server.env` | `deploy/env/server.env`（compose `env_file`） |
| 应用日志目录 | `/var/log/agent-forge`（`LOG_DIR`） | 卷 `apilogs` → 容器内 `/var/log/agent-forge` |
| 前端构建产物 | `/opt/agent-forge/web`（nginx `root`） | web 镜像内 `/usr/share/nginx/html` |
| 数据库数据目录 | `/var/lib/postgresql/16/main`（apt） | 卷 `pgdata` → `/var/lib/postgresql/data` |
| Redis 数据 | `/var/lib/redis` | 卷 `redisdata` → `/data` |
| Alembic 迁移 | `/opt/agent-forge/server/alembic`（+ `versions/`） | `/app/alembic` |
| uv 缓存（构建期） | `~agentforge/.cache/uv` | 镜像层 |
| nginx 站点配置 | `/etc/nginx/sites-available/agent-forge.conf` | web 容器 `/etc/nginx/conf.d/default.conf` |
| TLS 证书 | `/etc/letsencrypt/live/<域名>/` | 边缘代理处 |

> 注意：仓库里的 `server/pgdata/` 仅 dev `docker-compose.yml` 用，权限 `0700`、属主是容器内 postgres uid，**不要**在生产用它，也别让 `pytest` 递归进去（根 `pytest.ini` 已 `norecursedirs`）。

---

## 8. 【访问与操作权限要求】

**服务账号**：`agentforge`（system、`nologin`）。API 进程以它运行，绝不用 root。

**文件属主与权限**
| 路径 | owner | mode |
|---|---|---|
| `/opt/agent-forge`（代码） | `agentforge:agentforge` | `0755` |
| `/etc/agent-forge/server.env`（密钥） | `root:agentforge` | **`0640`**（仅服务用户可读） |
| `/var/log/agent-forge` | `agentforge:agentforge` | `0750` |
| `/opt/agent-forge/web`（静态） | `agentforge:agentforge`（nginx `www-data` 只需读） | `0755` |

**数据库权限（最小化）**：业务角色 `agentforge` 只是其库的 owner，**不是** superuser；不要用 postgres 超级用户跑应用。如需更严，可只授 `CONNECT`+`USAGE`+表级 CRUD，建表时用单独迁移角色。

**systemd 加固**（已在 unit 内）：`NoNewPrivileges`、`ProtectSystem=strict`、`ProtectHome`、`PrivateTmp`、`PrivateDevices`，唯一可写路径 `ReadWritePaths=/var/log/agent-forge`。

**网络/端口**：仅 80/443 对外；**API `127.0.0.1:8099`、Postgres `5432`、Redis `6379` 一律绑回环**，不对公网监听。防火墙：
```bash
sudo ufw allow 80,443/tcp && sudo ufw enable
```

**应用层访问控制（已实现，运行时强制）**：登录 `POST /auth/token`（密码，PBKDF2）；RBAC 与数据归属在 API 层强制（customer 只能看自己的 trace/plan；跨用户/跨租户访问返回 404；SSE 端点需 token + 租户校验）；写操作经策略引擎 + 人工确认，`dual` 需两名不同管理员投票。

**需要 sudo 的操作清单**：安装包、建服务用户、写 `/etc/agent-forge` 与 `/etc/systemd`、`systemctl`、nginx 配置与 reload、certbot、postgres 角色创建。**日常发布**（pull/build/migrate/reload）可由 `agentforge` 用户完成，仅 `systemctl reload` 需 sudo（可用 polkit/ sudoers 精确放行 `systemctl reload agent-forge-api`）。

---

## 9. 上线流程 / 零停机 / 回滚 / 备份 / 健康检查

**首次上线顺序**：建库角色 → 写 env → `alembic upgrade head` → `app.seed`（仅首次）→ 起 API → 构建并部署前端 → nginx+TLS → 设管理员密码。

**升级发布（零停机）**
```bash
cd /opt/agent-forge && sudo -u agentforge git pull
sudo -u agentforge bash -lc 'cd server && uv sync --no-dev'
sudo -u agentforge bash -lc 'cd server && set -a && . /etc/agent-forge/server.env && set +a && uv run alembic upgrade head'   # 迁移需向后兼容
npm ci && npm run build && sudo cp -r dist/* /opt/agent-forge/web/
sudo systemctl reload-or-restart agent-forge-api    # gunicorn 优雅滚动，老连接 drain
```
**回滚**：代码 `git checkout <上一个 tag>` + `uv sync` + `systemctl restart`；DB 用 `alembic downgrade <rev>`（仅当迁移可逆）。建议每次发布前 `pg_dump`。

**备份/恢复**
```bash
# 备份（含所有运营/审计/会话数据）
pg_dump -Fc -h 127.0.0.1 -U agentforge agentforge > /backup/agentforge_$(date +%F).dump
# 恢复
pg_restore -c -h 127.0.0.1 -U agentforge -d agentforge /backup/agentforge_YYYY-MM-DD.dump
```

**健康检查 / 探针**
- 存活：`GET /api/v1/health` → `{"status":"ok"}`。
- LLM 连通：`GET /api/v1/health/llm`（两个模型延迟/状态）。
- 就绪建议：在 LB/k8s 用 `/api/v1/health`；DB/Redis 不可用时 API 仍返回但业务接口会 5xx，看 journald。

---

## 10. 生产配置检查清单（上线前过一遍）

- [ ] `APP_ENV=prod`，`SECRET_KEY` ≥32 随机，`DEMO_LOGIN=false`
- [ ] `LLM_API_KEY` 已填；`/health/llm` 两模型 OK
- [ ] `DATABASE_URL` 指向真实主机 + 强密码（非 `agentforge:agentforge`）
- [ ] `CORS_ORIGINS` 精确到 https 域名，无 `*`
- [ ] `/etc/agent-forge/server.env` 为 `0640 root:agentforge`
- [ ] API/PG/Redis 仅回环监听；仅 80/443 对外
- [ ] 已创建真实管理员密码；demo `/auth/login` 返回 403
- [ ] 日志落 `/var/log/agent-forge` 且轮转生效；journald 限额已设
- [ ] `pg_dump` 定时备份已配置
- [ ] 后台探索任务：当前为进程内 `asyncio.create_task`（重启会丢未完成的探索）；高可用场景建议接 Arq/Celery 持久队列（roadmap）
