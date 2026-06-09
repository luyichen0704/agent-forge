# Ask Codex Input

## Question

为 /home/lmy/project/2605camel-business（agent-forge：前端 React/Vite 在 src/，后端 FastAPI+SQLAlchemy async+Postgres+Redis+SSE 在 server/，用 uv 管理；LLM 走 camel-hub）设计**生产**部署方案与可直接执行的运行手册。先读 server/（main.py、config.py、db.py、alembic、docker-compose.yml、pyproject.toml）、vite.config.ts、package.json、.gitignore，了解现状（现在是 dev：docker compose 起 pg/redis、uvicorn 直跑、role-login 无密码）。

产出（中文，每步给确切命令/配置范例，面向单机 systemd 与容器两种方案），并**完整覆盖**用户强制要求的三块：
1. 运行日志与详细日志的存放位置：uvicorn/gunicorn access+error、应用结构化日志、nginx access/error、postgres、redis、systemd journald 的**确切路径**、日志级别、轮转(logrotate/journald 配置)、如何查看。
2. 文件工作目录的具体路径：应用安装根目录、Python venv、前端构建产物 dist 的部署位置、env/密钥文件、数据库数据目录、redis 数据、alembic、uv 缓存、临时/上传目录——逐项给绝对路径。
3. 访问与操作权限要求：专用非登录服务用户、各目录/文件的 owner 与 mode、DB 角色最小权限授予 SQL、密钥文件 0640、systemd 加固指令(NoNewPrivileges/ProtectSystem/ReadWritePaths 等)、防火墙与端口暴露(仅 80/443，pg/redis/api 绑 127.0.0.1)、需要 sudo 的操作清单。

另外给出：gunicorn(uvicorn worker) 配置、systemd unit(api + 后台 worker)、nginx(TLS+SSE 透传+SPA fallback) 配置、docker-compose.prod.yml、数据库与迁移上线步骤、零停机发布与回滚、健康检查/就绪探针、备份与恢复。中文。

## Configuration

- Model: gpt-5.5
- Effort: high
- Timeout: 3600s
- Timestamp: 2026-06-09_23-57-57
