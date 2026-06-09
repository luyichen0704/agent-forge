以下是基于当前仓库现状整理的生产部署方案与运行手册。假设单机为 Ubuntu/Debian + systemd；容器方案为 Docker Compose 单机。当前代码要点：FastAPI 挂载 `/api/v1`，健康检查在 `/api/v1/health`；前端构建命令是 `npm run build`；Vite dev 代理 `/api` 到 `127.0.0.1:8099`；当前探索后台任务是 API 进程内 `asyncio.create_task`，仓库还没有独立 worker 入口，生产 worker 需要先队列化后启用。

**现状结论**
- 后端入口：`server/app/main.py:30`，API 路由统一前缀 `/api/v1` 在 `server/app/main.py:68`。
- 配置来源：`server/app/config.py:7` 使用环境变量或 `.env`，当前 dev 默认 DB/Redis 在 `server/app/config.py:14`。
- 数据库：SQLAlchemy async engine 在 `server/app/db.py:7`，Alembic 使用同步 URL 跑迁移。
- SSE：探索事件 SSE 路径在 `server/app/api/sources.py:68`；探索任务当前由 API 内部 task 启动在 `server/app/api/sources.py:49`。
- 前端：生产构建命令 `npm run build` 来自 `package.json:8`；前端 API 使用同源 `/api/v1`，生产由 nginx 代理即可。
- dev compose：`server/docker-compose.yml:9` 公开 Postgres `5544`，`server/docker-compose.yml:22` 公开 Redis `6390`，生产不要这样暴露。
- 已有生产草稿：`server/gunicorn.conf.py:1`、`deploy/nginx/agent-forge.conf:1`、`docker-compose.prod.yml:1` 可作为基础，但下面手册补齐日志、权限、备份、回滚和 worker 注意事项。

**一、生产目录规划**
统一使用这些绝对路径，后续命令都按此执行：

| 项目 | 路径 | owner / mode |
|---|---|---|
| 应用安装根目录 | `/opt/agent-forge` | `root:agentforge` / `0755` |
| 发布版本目录 | `/opt/agent-forge/releases/<release_id>` | `root:agentforge` / dir `0755` file `0644` |
| 当前版本软链 | `/opt/agent-forge/current` | 指向当前 release |
| 后端工作目录 | `/opt/agent-forge/current/server` | `root:agentforge` / `0755` |
| Python venv | `/opt/agent-forge/current/server/.venv` | `root:agentforge` / `0755` |
| 前端构建产物源 | `/opt/agent-forge/current/dist` | `root:agentforge` / `0755` |
| nginx 静态站点目录 | `/opt/agent-forge/shared/web` | `root:www-data` / dir `0755` file `0644` |
| env/密钥文件 | `/etc/agent-forge/server.env` | `root:agentforge` / `0640` |
| migration 专用密钥 | `/etc/agent-forge/migration.env` | `root:agentforge` / `0640` |
| Alembic 目录 | `/opt/agent-forge/current/server/alembic` | `root:agentforge` / `0755` |
| Alembic 配置 | `/opt/agent-forge/current/server/alembic.ini` | `root:agentforge` / `0644` |
| uv 缓存 | `/var/cache/agent-forge/uv` | `agentforge:agentforge` / `0750` |
| 应用临时目录 | `/var/lib/agent-forge/tmp` | `agentforge:agentforge` / `0750` |
| 上传/文件目录 | `/var/lib/agent-forge/uploads` | `agentforge:agentforge` / `0750` |
| 应用日志目录 | `/var/log/agent-forge` | `agentforge:agentforge` / `0750` |
| Postgres 数据 | `/var/lib/postgresql/16/main` | `postgres:postgres` / `0700` |
| Redis 数据 | `/var/lib/redis` | `redis:redis` / `0750` |
| 备份目录 | `/var/backups/agent-forge` | `root:agentforge` / `0750` |

创建目录与服务用户：

```bash
sudo groupadd --system agentforge || true
sudo useradd --system --gid agentforge --home /opt/agent-forge --shell /usr/sbin/nologin agentforge || true

sudo install -d -o root -g agentforge -m 0755 /opt/agent-forge
sudo install -d -o root -g agentforge -m 0755 /opt/agent-forge/releases
sudo install -d -o root -g www-data   -m 0755 /opt/agent-forge/shared/web
sudo install -d -o root -g agentforge -m 0750 /etc/agent-forge
sudo install -d -o agentforge -g agentforge -m 0750 /var/cache/agent-forge/uv
sudo install -d -o agentforge -g agentforge -m 0750 /var/lib/agent-forge/tmp
sudo install -d -o agentforge -g agentforge -m 0750 /var/lib/agent-forge/uploads
sudo install -d -o agentforge -g agentforge -m 0750 /var/log/agent-forge
sudo install -d -o root -g agentforge -m 0750 /var/backups/agent-forge/postgres
sudo install -d -o root -g agentforge -m 0750 /var/backups/agent-forge/redis
sudo install -d -o root -g agentforge -m 0750 /var/backups/agent-forge/uploads
```

**二、生产环境变量**
`/etc/agent-forge/server.env`：

```bash
APP_ENV=prod
SECRET_KEY=__REPLACE_WITH_RANDOM_48_PLUS_CHARS__

DATABASE_URL=postgresql+asyncpg://agentforge_app:__APP_DB_PASSWORD__@127.0.0.1:5432/agentforge
SYNC_DATABASE_URL=postgresql+psycopg://agentforge_app:__APP_DB_PASSWORD__@127.0.0.1:5432/agentforge

REDIS_URL=redis://:__REDIS_PASSWORD__@127.0.0.1:6379/0

LLM_BASE_URL=https://api.camel-hub.com/v1
LLM_API_KEY=__CAMEL_HUB_KEY__
PLLM_MODEL=claude-sonnet-4-5
QLLM_MODEL=claude-haiku-4-5

CORS_ORIGINS=https://agent-forge.example.com

LOG_DIR=/var/log/agent-forge
LOG_LEVEL=INFO
LOG_JSON=true

DEMO_LOGIN=false
SESSION_TTL_DAYS=7

API_BIND=127.0.0.1:8099
WEB_CONCURRENCY=5
GUNICORN_TIMEOUT=180
GUNICORN_ACCESS_LOG=/var/log/agent-forge/gunicorn-access.log
GUNICORN_ERROR_LOG=/var/log/agent-forge/gunicorn-error.log

UV_CACHE_DIR=/var/cache/agent-forge/uv
TMPDIR=/var/lib/agent-forge/tmp
UPLOAD_DIR=/var/lib/agent-forge/uploads
```

`/etc/agent-forge/migration.env`：

```bash
APP_ENV=prod
SECRET_KEY=__SAME_SECRET_KEY__
DATABASE_URL=postgresql+asyncpg://agentforge_owner:__OWNER_DB_PASSWORD__@127.0.0.1:5432/agentforge
SYNC_DATABASE_URL=postgresql+psycopg://agentforge_owner:__OWNER_DB_PASSWORD__@127.0.0.1:5432/agentforge
REDIS_URL=redis://:__REDIS_PASSWORD__@127.0.0.1:6379/0
LLM_BASE_URL=https://api.camel-hub.com/v1
LLM_API_KEY=__CAMEL_HUB_KEY__
CORS_ORIGINS=https://agent-forge.example.com
DEMO_LOGIN=false
```

权限：

```bash
sudo chown root:agentforge /etc/agent-forge/server.env /etc/agent-forge/migration.env
sudo chmod 0640 /etc/agent-forge/server.env /etc/agent-forge/migration.env
```

生成 secret：

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

**三、Postgres 最小权限**
安装并限制监听本机：

```bash
sudo apt-get update
sudo apt-get install -y postgresql-16 postgresql-client-16

sudo sed -i "s/^#*listen_addresses.*/listen_addresses = '127.0.0.1'/" /etc/postgresql/16/main/postgresql.conf
sudo tee -a /etc/postgresql/16/main/postgresql.conf >/dev/null <<'EOF'
log_directory = '/var/log/postgresql'
log_filename = 'postgresql-16-main.log'
log_min_messages = warning
log_min_duration_statement = 500
log_statement = 'none'
EOF

sudo systemctl restart postgresql
```

创建 owner/app 角色：

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE agentforge_owner LOGIN PASSWORD '__OWNER_DB_PASSWORD__';
CREATE ROLE agentforge_app LOGIN PASSWORD '__APP_DB_PASSWORD__';

CREATE DATABASE agentforge OWNER agentforge_owner;

\c agentforge

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO agentforge_app;
GRANT CONNECT ON DATABASE agentforge TO agentforge_app;

ALTER DEFAULT PRIVILEGES FOR ROLE agentforge_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agentforge_app;

ALTER DEFAULT PRIVILEGES FOR ROLE agentforge_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO agentforge_app;
SQL
```

跑完 Alembic 后补授予已存在对象：

```bash
sudo -u postgres psql -d agentforge <<'SQL'
GRANT USAGE ON SCHEMA public TO agentforge_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agentforge_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agentforge_app;
SQL
```

`pg_hba.conf` 建议只允许本机：

```bash
sudo tee -a /etc/postgresql/16/main/pg_hba.conf >/dev/null <<'EOF'
host    agentforge    agentforge_owner    127.0.0.1/32    scram-sha-256
host    agentforge    agentforge_app      127.0.0.1/32    scram-sha-256
EOF
sudo systemctl reload postgresql
```

**四、Redis 配置**
安装并限制监听本机：

```bash
sudo apt-get install -y redis-server

sudo sed -i "s/^bind .*/bind 127.0.0.1 ::1/" /etc/redis/redis.conf
sudo sed -i "s/^protected-mode .*/protected-mode yes/" /etc/redis/redis.conf
sudo sed -i "s#^dir .*#dir /var/lib/redis#" /etc/redis/redis.conf
sudo sed -i "s#^logfile .*#logfile /var/log/redis/redis-server.log#" /etc/redis/redis.conf
sudo sed -i "s/^loglevel .*/loglevel notice/" /etc/redis/redis.conf
sudo sed -i "s/^# requirepass .*/requirepass __REDIS_PASSWORD__/" /etc/redis/redis.conf

sudo systemctl restart redis-server
```

**五、构建与安装 release**
在代码目录执行：

```bash
RELEASE_ID=$(date +%Y%m%d%H%M%S)
RELEASE_DIR=/opt/agent-forge/releases/$RELEASE_ID

sudo install -d -o root -g agentforge -m 0755 "$RELEASE_DIR"

sudo rsync -a --delete \
  --exclude .git \
  --exclude node_modules \
  --exclude dist \
  --exclude server/.venv \
  --exclude server/.env \
  --exclude server/pgdata \
  ./ "$RELEASE_DIR/"

sudo chown -R root:agentforge "$RELEASE_DIR"
sudo find "$RELEASE_DIR" -type d -exec chmod 0755 {} +
sudo find "$RELEASE_DIR" -type f -exec chmod 0644 {} +
```

安装 Python 依赖：

```bash
cd "$RELEASE_DIR/server"
sudo -u agentforge bash -lc '
  export UV_CACHE_DIR=/var/cache/agent-forge/uv
  uv sync --frozen --no-dev
'
```

构建前端并部署静态产物：

```bash
cd "$RELEASE_DIR"
npm ci
npm run build

sudo rsync -a --delete dist/ /opt/agent-forge/shared/web/
sudo chown -R root:www-data /opt/agent-forge/shared/web
sudo find /opt/agent-forge/shared/web -type d -exec chmod 0755 {} +
sudo find /opt/agent-forge/shared/web -type f -exec chmod 0644 {} +
```

切换 current：

```bash
sudo ln -sfn "$RELEASE_DIR" /opt/agent-forge/current
```

**六、Gunicorn 配置**
建议放在 `/opt/agent-forge/current/server/gunicorn.conf.py`：

```python
import multiprocessing
import os

bind = os.getenv("API_BIND", "127.0.0.1:8099")
workers = int(os.getenv("WEB_CONCURRENCY", str(multiprocessing.cpu_count() * 2 + 1)))
worker_class = "uvicorn.workers.UvicornWorker"

timeout = int(os.getenv("GUNICORN_TIMEOUT", "180"))
graceful_timeout = 30
keepalive = 15

max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "0"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "0"))

accesslog = os.getenv("GUNICORN_ACCESS_LOG", "/var/log/agent-forge/gunicorn-access.log")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "/var/log/agent-forge/gunicorn-error.log")
loglevel = os.getenv("LOG_LEVEL", "INFO").lower()
proc_name = "agent-forge-api"
```

说明：当前探索任务在 API worker 内执行，若保留这种实现，建议 `GUNICORN_MAX_REQUESTS=0`，避免 worker recycle 杀掉长任务。生产更推荐把 `server/app/api/sources.py:49` 的 in-process task 改成 Redis 队列 + 独立 worker。

**七、systemd API unit**
`/etc/systemd/system/agent-forge-api.service`：

```ini
[Unit]
Description=agent-forge API (FastAPI/Gunicorn)
After=network-online.target postgresql.service redis-server.service
Wants=network-online.target

[Service]
Type=exec
User=agentforge
Group=agentforge
WorkingDirectory=/opt/agent-forge/current/server
EnvironmentFile=/etc/agent-forge/server.env
ExecStart=/opt/agent-forge/current/server/.venv/bin/gunicorn -c gunicorn.conf.py app.main:app

Restart=always
RestartSec=3
TimeoutStopSec=45
KillSignal=SIGTERM

StandardOutput=journal
StandardError=journal
SyslogIdentifier=agent-forge-api

NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=false
ReadWritePaths=/var/log/agent-forge /var/lib/agent-forge /var/cache/agent-forge/uv /run/agent-forge

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now agent-forge-api
sudo systemctl status agent-forge-api --no-pager
```

**八、systemd 后台 worker unit**
当前仓库没有独立 worker 入口；不要伪装成已可运行。生产目标是把探索任务从 `asyncio.create_task` 改为 Redis durable queue，例如实现 `python -m app.worker` 后启用以下 unit。

`/etc/systemd/system/agent-forge-worker.service`：

```ini
[Unit]
Description=agent-forge background worker
After=network-online.target postgresql.service redis-server.service
Wants=network-online.target

[Service]
Type=exec
User=agentforge
Group=agentforge
WorkingDirectory=/opt/agent-forge/current/server
EnvironmentFile=/etc/agent-forge/server.env
ExecStart=/opt/agent-forge/current/server/.venv/bin/python -m app.worker

Restart=always
RestartSec=3
TimeoutStopSec=60

StandardOutput=journal
StandardError=journal
SyslogIdentifier=agent-forge-worker

NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
ReadWritePaths=/var/log/agent-forge /var/lib/agent-forge /var/cache/agent-forge/uv /run/agent-forge

[Install]
WantedBy=multi-user.target
```

启用前必须验证：

```bash
sudo -u agentforge bash -lc '
  cd /opt/agent-forge/current/server
  set -a; source /etc/agent-forge/server.env; set +a
  .venv/bin/python -m app.worker --help
'
```

通过后启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now agent-forge-worker
```

若暂未改造 worker，生产可先只启用 `agent-forge-api`，但要接受：API worker 重启会中断正在执行的探索任务。

**九、nginx TLS + SSE + SPA**
`/etc/nginx/conf.d/agent-forge-upstream.conf`：

```nginx
upstream agent_forge_api {
    server 127.0.0.1:8099;
    keepalive 32;
}
```

`/etc/nginx/sites-available/agent-forge.conf`：

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    "" close;
}

server {
    listen 80;
    server_name agent-forge.example.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name agent-forge.example.com;

    ssl_certificate     /etc/letsencrypt/live/agent-forge.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agent-forge.example.com/privkey.pem;

    root /opt/agent-forge/shared/web;
    index index.html;

    access_log /var/log/nginx/agent-forge.access.log;
    error_log  /var/log/nginx/agent-forge.error.log warn;

    client_max_body_size 10m;

    location /api/v1/exploration-jobs/ {
        proxy_pass http://agent_forge_api;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_set_header Host $host;
        proxy_set_header X-Request-ID $request_id;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://agent_forge_api;
        proxy_http_version 1.1;
        proxy_read_timeout 180s;
        proxy_send_timeout 180s;
        proxy_set_header Host $host;
        proxy_set_header X-Request-ID $request_id;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

启用：

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo ln -sfn /etc/nginx/sites-available/agent-forge.conf /etc/nginx/sites-enabled/agent-forge.conf
sudo nginx -t
sudo systemctl reload nginx
```

申请证书示例：

```bash
sudo certbot --nginx -d agent-forge.example.com
```

**十、日志路径、级别、轮转、查看**
生产日志必须落在以下路径：

| 日志 | 路径 | 级别 | 查看 |
|---|---|---|---|
| Gunicorn access | `/var/log/agent-forge/gunicorn-access.log` | access 全量 | `sudo tail -f /var/log/agent-forge/gunicorn-access.log` |
| Gunicorn error | `/var/log/agent-forge/gunicorn-error.log` | `INFO` | `sudo tail -f /var/log/agent-forge/gunicorn-error.log` |
| 应用结构化日志 | `/var/log/agent-forge/app.log` | `LOG_LEVEL=INFO`, `LOG_JSON=true` | `sudo tail -f /var/log/agent-forge/app.log` |
| nginx access | `/var/log/nginx/agent-forge.access.log` | access 全量 | `sudo tail -f /var/log/nginx/agent-forge.access.log` |
| nginx error | `/var/log/nginx/agent-forge.error.log` | `warn` | `sudo tail -f /var/log/nginx/agent-forge.error.log` |
| Postgres | `/var/log/postgresql/postgresql-16-main.log` | `warning` + 慢查询 `500ms` | `sudo tail -f /var/log/postgresql/postgresql-16-main.log` |
| Redis | `/var/log/redis/redis-server.log` | `notice` | `sudo tail -f /var/log/redis/redis-server.log` |
| systemd journald | `/var/log/journal/` | unit stdout/stderr | `sudo journalctl -u agent-forge-api -f` |

应用 logrotate：`/etc/logrotate.d/agent-forge`：

```conf
/var/log/agent-forge/*.log {
    daily
    rotate 14
    missingok
    notifempty
    compress
    delaycompress
    create 0640 agentforge agentforge
    sharedscripts
    postrotate
        systemctl kill -s HUP agent-forge-api.service >/dev/null 2>&1 || true
    endscript
}
```

nginx logrotate：`/etc/logrotate.d/agent-forge-nginx`：

```conf
/var/log/nginx/agent-forge.*.log {
    daily
    rotate 30
    missingok
    notifempty
    compress
    delaycompress
    create 0640 www-data adm
    sharedscripts
    postrotate
        systemctl reload nginx >/dev/null 2>&1 || true
    endscript
}
```

journald 持久化与限制：`/etc/systemd/journald.conf.d/agent-forge.conf`：

```ini
[Journal]
Storage=persistent
SystemMaxUse=2G
SystemKeepFree=1G
MaxRetentionSec=30day
Compress=yes
```

应用：

```bash
sudo install -d -m 0755 /etc/systemd/journald.conf.d
sudo systemctl restart systemd-journald
```

查看常用命令：

```bash
sudo journalctl -u agent-forge-api --since "1 hour ago"
sudo journalctl -u agent-forge-api -f
sudo journalctl -u nginx -f
sudo tail -f /var/log/agent-forge/app.log
sudo tail -f /var/log/nginx/agent-forge.error.log
sudo tail -f /var/log/postgresql/postgresql-16-main.log
sudo tail -f /var/log/redis/redis-server.log
```

**十一、迁移与首次上线**
安装依赖并跑迁移：

```bash
sudo -u agentforge bash -lc '
  cd /opt/agent-forge/current/server
  set -a; source /etc/agent-forge/migration.env; set +a
  export UV_CACHE_DIR=/var/cache/agent-forge/uv
  .venv/bin/alembic current
  .venv/bin/alembic upgrade head
'
```

补授权：

```bash
sudo -u postgres psql -d agentforge <<'SQL'
GRANT USAGE ON SCHEMA public TO agentforge_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agentforge_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agentforge_app;
SQL
```

首次初始化数据：生产不要使用无密码 demo role-login。若必须导入演示数据，仅在隔离环境执行：

```bash
sudo -u agentforge bash -lc '
  cd /opt/agent-forge/current/server
  set -a; source /etc/agent-forge/migration.env; set +a
  .venv/bin/python -m app.seed
'
```

生产用户应使用密码/OIDC。若采用当前密码登录草稿，需要先确保已禁用 `DEMO_LOGIN=false`，并创建带 `password_hash` 的用户。

**十二、防火墙与端口暴露**
单机 systemd 方案只公开 `80/443`：

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

必须保持：

```bash
ss -lntp | grep -E ':(80|443|8099|5432|6379)\b'
```

预期：
- nginx：`0.0.0.0:80`、`0.0.0.0:443`
- API：`127.0.0.1:8099`
- Postgres：`127.0.0.1:5432`
- Redis：`127.0.0.1:6379`

**十三、容器生产方案**
建议项目部署根目录：`/opt/agent-forge-compose`。宿主机持久化路径：

| 项目 | 宿主机路径 | 容器内路径 |
|---|---|---|
| compose 根 | `/opt/agent-forge-compose` | - |
| env | `/opt/agent-forge-compose/deploy/env/server.env` | API env file |
| Postgres 数据 | `/srv/agent-forge/postgres` | `/var/lib/postgresql/data` |
| Redis 数据 | `/srv/agent-forge/redis` | `/data` |
| API 日志 | `/srv/agent-forge/logs/api` | `/var/log/agent-forge` |
| nginx 日志 | `/srv/agent-forge/logs/nginx` | `/var/log/nginx` |
| 备份 | `/srv/agent-forge/backups` | 按需挂载 |

创建目录：

```bash
sudo install -d -o root -g root -m 0755 /opt/agent-forge-compose
sudo install -d -o 999 -g 999 -m 0700 /srv/agent-forge/postgres
sudo install -d -o 999 -g 999 -m 0750 /srv/agent-forge/redis
sudo install -d -o 10001 -g 10001 -m 0750 /srv/agent-forge/logs/api
sudo install -d -o root -g root -m 0755 /srv/agent-forge/logs/nginx
sudo install -d -o root -g root -m 0750 /srv/agent-forge/backups
```

`docker-compose.prod.yml` 示例：

```yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: agentforge_owner
      POSTGRES_PASSWORD: ${POSTGRES_OWNER_PASSWORD:?set}
      POSTGRES_DB: agentforge
    volumes:
      - /srv/agent-forge/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentforge_owner -d agentforge"]
      interval: 5s
      timeout: 3s
      retries: 20
    logging:
      driver: json-file
      options: { max-size: "50m", max-file: "5" }

  redis:
    image: redis:7
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--requirepass", "${REDIS_PASSWORD:?set}"]
    volumes:
      - /srv/agent-forge/redis:/data
    healthcheck:
      test: ["CMD-SHELL", "redis-cli -a \"$${REDIS_PASSWORD}\" ping || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 20
    environment:
      REDIS_PASSWORD: ${REDIS_PASSWORD:?set}
    logging:
      driver: json-file
      options: { max-size: "50m", max-file: "5" }

  api:
    build: ./server
    restart: unless-stopped
    env_file:
      - deploy/env/server.env
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
    volumes:
      - /srv/agent-forge/logs/api:/var/log/agent-forge
    expose:
      - "8099"
    healthcheck:
      test: ["CMD-SHELL", "python - <<'PY'\nimport urllib.request\nurllib.request.urlopen('http://127.0.0.1:8099/api/v1/health', timeout=3)\nPY"]
      interval: 10s
      timeout: 5s
      retries: 12
    logging:
      driver: json-file
      options: { max-size: "50m", max-file: "5" }

  web:
    build:
      context: .
      dockerfile: web.Dockerfile
    restart: unless-stopped
    depends_on:
      api: { condition: service_healthy }
    ports:
      - "80:80"
    volumes:
      - /srv/agent-forge/logs/nginx:/var/log/nginx
    logging:
      driver: json-file
      options: { max-size: "50m", max-file: "5" }
```

容器 env 中 DB/Redis 主机使用服务名：

```bash
DATABASE_URL=postgresql+asyncpg://agentforge_app:__APP_DB_PASSWORD__@db:5432/agentforge
SYNC_DATABASE_URL=postgresql+psycopg://agentforge_app:__APP_DB_PASSWORD__@db:5432/agentforge
REDIS_URL=redis://:__REDIS_PASSWORD__@redis:6379/0
```

启动：

```bash
cd /opt/agent-forge-compose
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
docker compose -f docker-compose.prod.yml ps
```

容器内迁移：

```bash
docker compose -f docker-compose.prod.yml run --rm \
  --env-file deploy/env/migration.env \
  api alembic upgrade head
```

查看日志：

```bash
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f db
docker compose -f docker-compose.prod.yml logs -f redis
sudo tail -f /srv/agent-forge/logs/api/app.log
sudo tail -f /srv/agent-forge/logs/nginx/access.log
```

Docker daemon 日志轮转：`/etc/docker/daemon.json`：

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  }
}
```

应用：

```bash
sudo systemctl restart docker
```

**十四、健康检查与就绪探针**
当前直接可用：

```bash
curl -fsS http://127.0.0.1:8099/api/v1/health
curl -fsS https://agent-forge.example.com/api/v1/health
curl -fsS https://agent-forge.example.com/api/v1/health/llm
```

DB/Redis 就绪：

```bash
pg_isready -h 127.0.0.1 -p 5432 -d agentforge -U agentforge_app
redis-cli -h 127.0.0.1 -a '__REDIS_PASSWORD__' ping
```

生产建议新增 `/api/v1/readyz`，检查：
- DB `SELECT 1`
- Redis `PING`
- Alembic revision 是否为 head
- camel-hub 可选轻量探测

**十五、零停机发布**
单机推荐蓝绿端口切换。

1. 当前版本运行在 `127.0.0.1:8099`。
2. 新 release 构建到 `/opt/agent-forge/releases/<new>`。
3. 用临时 env 让新 API 跑 `8100`：

```bash
sudo cp /etc/agent-forge/server.env /etc/agent-forge/server-8100.env
sudo sed -i 's/API_BIND=.*/API_BIND=127.0.0.1:8100/' /etc/agent-forge/server-8100.env
sudo chmod 0640 /etc/agent-forge/server-8100.env
sudo chown root:agentforge /etc/agent-forge/server-8100.env
```

4. 创建临时 service 或使用模板 service 启动新版本。
5. 跑迁移，要求迁移兼容旧代码：

```bash
sudo -u agentforge bash -lc '
  cd /opt/agent-forge/current/server
  set -a; source /etc/agent-forge/migration.env; set +a
  .venv/bin/alembic upgrade head
'
```

6. 健康检查新端口：

```bash
curl -fsS http://127.0.0.1:8100/api/v1/health
```

7. 切换 nginx upstream：

```bash
sudo sed -i 's/server 127.0.0.1:8099;/server 127.0.0.1:8100;/' /etc/nginx/conf.d/agent-forge-upstream.conf
sudo nginx -t
sudo systemctl reload nginx
```

8. 观察：

```bash
sudo tail -f /var/log/nginx/agent-forge.error.log
sudo journalctl -u agent-forge-api -f
```

9. 停旧进程。

回滚：
- 应用回滚：把 nginx upstream 改回旧端口并 reload。
- 文件回滚：`sudo ln -sfn /opt/agent-forge/releases/<old> /opt/agent-forge/current && sudo systemctl restart agent-forge-api`。
- DB 回滚：只在迁移不可兼容且已评估数据损失时，从备份恢复；常规生产发布应使用向前兼容迁移，避免 DB rollback。

**十六、备份与恢复**
Postgres 备份：

```bash
BACKUP=/var/backups/agent-forge/postgres/agentforge-$(date +%Y%m%d%H%M%S).dump
sudo -u postgres pg_dump -Fc -d agentforge -f "$BACKUP"
sudo chown root:agentforge "$BACKUP"
sudo chmod 0640 "$BACKUP"
```

Postgres 恢复到空库：

```bash
sudo systemctl stop agent-forge-api
sudo -u postgres dropdb agentforge
sudo -u postgres createdb -O agentforge_owner agentforge
sudo -u postgres pg_restore -d agentforge /var/backups/agent-forge/postgres/agentforge-YYYYMMDDHHMMSS.dump

sudo -u postgres psql -d agentforge <<'SQL'
GRANT USAGE ON SCHEMA public TO agentforge_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agentforge_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agentforge_app;
SQL

sudo systemctl start agent-forge-api
```

Redis 备份：

```bash
redis-cli -h 127.0.0.1 -a '__REDIS_PASSWORD__' SAVE
sudo cp /var/lib/redis/dump.rdb /var/backups/agent-forge/redis/dump-$(date +%Y%m%d%H%M%S).rdb
sudo chown root:agentforge /var/backups/agent-forge/redis/*.rdb
sudo chmod 0640 /var/backups/agent-forge/redis/*.rdb
```

上传目录备份：

```bash
sudo tar -C /var/lib/agent-forge -czf /var/backups/agent-forge/uploads/uploads-$(date +%Y%m%d%H%M%S).tar.gz uploads
sudo chown root:agentforge /var/backups/agent-forge/uploads/*.tar.gz
sudo chmod 0640 /var/backups/agent-forge/uploads/*.tar.gz
```

容器 DB 备份：

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U agentforge_owner -Fc agentforge \
  > /srv/agent-forge/backups/agentforge-$(date +%Y%m%d%H%M%S).dump
```

**十七、需要 sudo 的操作清单**
- 创建服务用户、系统目录、日志目录、备份目录。
- 安装/配置 Postgres、Redis、nginx、certbot、Docker。
- 写入 `/etc/agent-forge/*.env`、`/etc/systemd/system/*.service`、`/etc/nginx/*`。
- 修改防火墙 `ufw`。
- `systemctl daemon-reload/start/restart/reload`。
- 绑定 80/443、申请 TLS 证书。
- 读取系统日志、数据库日志、nginx 日志。
- 执行数据库备份/恢复与权限授予。

**十八、上线前硬性检查**
- `DEMO_LOGIN=false`，不能使用无密码 role-login。
- `SECRET_KEY`、`LLM_API_KEY`、DB/Redis 密码只在 `0640` env 文件中。
- 公网只开放 `80/443`。
- API、Postgres、Redis 均绑定 `127.0.0.1` 或仅容器内网络。
- Alembic 已 `upgrade head`。
- `/api/v1/health`、DB、Redis、camel-hub 检查通过。
- 日志路径、logrotate、journald 持久化已配置。
- 至少完成一次备份恢复演练。
