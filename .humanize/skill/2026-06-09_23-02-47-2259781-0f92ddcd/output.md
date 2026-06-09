以下是静态代码审查结果，重点只列“真实可触发/会造成安全或一致性影响”的问题。未修改代码、未运行测试。

**Critical**
- `server/app/api/sources.py:64`：SSE `/exploration-jobs/{job_id}/events` 完全无鉴权，也不校验 `job.tenant_id`；任何人拿到 UUID 就能读取探索事件。修法：给路由加 `p: Principal = Depends(get_principal)`，或实现专用短期 SSE token；进入流前和循环内都校验 job 属于 `p.tenant_id`，不存在返回 404。
- `src/features/sources.ts:42`：前端把 token 放进 `?token=`，但后端未读取；即使读取也会泄露到日志/Referer/历史记录。修法：优先使用 HttpOnly SameSite Cookie；或用支持 header 的 SSE polyfill，通过 `Authorization` 传 token。
- `server/app/api/chat.py:119`、`server/app/api/chat.py:129`、`server/app/api/chat.py:143`：`get_plan/confirm/cancel` 只按 `plan_id` 取计划，不校验所属 `ChatSession.user_id/tenant_id`；存在跨用户读取、执行、取消计划的 IDOR。修法：查询时 join `execution_plans -> chat_sessions`，要求 `session.user_id == p.user.id` 且 `tenant_id == p.tenant_id`；管理员跨用户查看也应走显式审计授权。
- `server/app/api/traces.py:18`、`server/app/api/traces.py:29`：Trace 只按 tenant 授权，customer 可列出并读取同租户所有 trace/audit/flow，审计 payload 里含用户指令和执行细节。修法：按角色收敛：customer 只能看 `actor_id == p.user.id` 或 dataflow reader 允许的 trace；employee/admin 才能看租户级；payload 做字段级脱敏。
- `server/app/api/identity.py:23`：登录接口只传 `role`，无需密码/身份凭据即可获取 admin token。修法：生产环境移除 demo role-login；改为邮箱+密码/OIDC；登录时校验 `UserRole`，并禁止任意选择非本人拥有的角色。

**High**
- `server/app/agents/orchestrator.py:167`：`confirm_plan` 未锁定 plan/steps/approval/execution，两个并发确认可同时通过状态检查并重复执行写操作、重复追加审计事件。修法：用 `async with db.begin()`，`select(ExecutionPlan).with_for_update()` 锁计划，锁相关 `PlanStep/ApprovalRequest`；状态从 `awaiting_confirm` 原子切到 `executing` 后再执行。
- `server/app/models/execution.py:51`、`server/alembic/versions/62527d79c8f6_initial_schema.py:436`：`idempotency_key` 只有普通索引，不唯一；无法防止重复执行记录。修法：加唯一约束/部分唯一索引 `executions(idempotency_key) where idempotency_key is not null`，执行前按 key 查重并返回已有结果。
- `server/app/api/chat.py:133`、`server/app/agents/orchestrator.py:167`：任何已登录用户只要能拿到 plan UUID 就能触发 `confirm_plan`，且 `confirm_plan` 不校验 approver 角色/是否计划所有者/是否有审批权限。修法：确认动作必须校验 plan 所属用户或管理员权限；执行前重新校验所有审批请求已由合法管理员完成。
- `server/app/agents/orchestrator.py:93`、`server/app/services/planner.py:87`：P-LLM 输出的 `op_key` 没有强制校验必须来自 registry；admin 可生成未知 write，审批后 `confirm_plan` 找不到 op 时仍走默认 `FunctionExecutor`。修法：normalise 后验证每个非 parse step 的 `op_key in op_by_key` 且 kind 匹配；未知操作直接 `POLICY_DENIED`。
- `server/app/agents/orchestrator.py:100`、`server/app/policies/engine.py:63`：策略引擎注入的 `decision.injected` 从未写入 `PlanStep.input_refs_json`，ABAC/self scope 实际不生效。修法：将 `decision.injected` 合并进执行参数；executor 查询必须强制 `owner_user_id == identity.user_id`，不能只靠 LLM 计划。
- `server/app/agents/orchestrator.py:196`、`server/app/executors/base.py:54`：query/parse 步骤根本没有执行，Q-LLM `qparser.parse` 未被 orchestrator 调用，write 执行参数是空 `{}`；CaMeL 的 P/Q 隔离在主流程中基本没有落地。修法：实现 query step 数据读取、parse step 调用 `qparser.parse` 并携带能力标签、write step 只消费显式 data refs/parsed refs。
- `server/app/api/chat.py:108`、`server/app/agents/orchestrator.py:140`：auto plan 只被标成 `confirmed`，并未自动调用 `confirm_plan`，但前端/回复文案说“已自动执行”。修法：无写/auto 计划创建后立即执行只读流程并置 `done`，或文案改为“已生成计划，待执行”。
- `server/app/api/sources.py:49`：`asyncio.create_task(run_exploration(...))` 是进程内 fire-and-forget；服务重启任务丢失，异常未观测。修法：使用 Celery/RQ/Arq/FastAPI BackgroundTasks 至少保存任务状态；给 task 加 done callback 记录异常。
- `server/app/services/explorer.py:47`：`run_exploration` 只捕获 `LLMError`，其他异常会让 job/source 永久卡在 running。修法：包一层 broad `except Exception`，写 `ExplorationEvent(error)`，`job.status='error'`，`source.status='error'` 并 commit。
- `server/app/deps.py:41`、`server/app/models/identity.py:63`：请求鉴权信任 `Session.acting_role`，没有重新校验用户仍拥有该角色。修法：`get_principal` join `roles/user_roles` 校验 `sess.acting_role` 属于当前用户且同租户；角色变更后应使旧 session 失效。
- `server/app/api/approvals.py:51`：审批投票没有 `FOR UPDATE` 锁 `ApprovalRequest`，也不检查过期时间；并发/过期审批状态可能不一致。修法：投票事务内 `select ApprovalRequest ... with_for_update()`，检查 `expires_at > now`，状态转换一次性完成。
- `server/app/api/executions.py:36`：rollback 只允许 employee/admin，但不校验原 execution 是否可回滚、是否已经有补偿记录并发创建；`FunctionExecutor.rollback` 也没有实际恢复 `BizRecord`。修法：锁 execution，唯一约束 `rolls_back_execution_id`，executor rollback 根据 before_state 定位并恢复真实业务行。

**Medium**
- `server/app/services/audit.py:41`：审计链用 `Trace FOR UPDATE` 在 Postgres 同一事务内能串行化 seq；但没有 `IntegrityError` 重试，也无法防止绕过 `append_event` 的直接插入。修法：保留锁，加 retry；收紧 DB 权限，应用层只暴露 append 函数；必要时用 DB trigger 维护 seq/hash。
- `server/app/api/approvals.py:56`：dual approval 确实因 `uq_vote_once` 要两个不同 `approver_id`，但没有禁止 `requested_by` 自批，且 demo seed 只有一个 admin 会导致 dual 永远无法完成。修法：`required_votes=2` 时排除 `requested_by`，并在租户内要求至少两个 admin；或支持审批组。
- `server/app/api/approvals.py:46`：`decision` 未限制枚举，传非 `approve/reject` 会写入无效投票且请求保持 pending。修法：Pydantic 用 `Literal["approve","reject"]`。
- `server/app/api/registry.py:64`：`get_operation` 对非 admin 不按 `OperationPermission` 过滤，知道 op UUID 即可读取同租户不可调用操作。修法：复用 list 的角色过滤；敏感字段如 executor/policy_ref 对非 admin 脱敏。
- `server/app/agents/orchestrator.py:31`、`server/app/api/registry.py:36`、`server/app/api/plugins.py:24`：多处 N+1 查询权限/插件注册，数据量大时明显退化。修法：用 join/selectinload，一次拉取 `OperationPermission`/`PluginRegistration` 后按 id 分组。
- `server/app/services/explorer.py:34`：探索事件 seq 用 `max(seq)+1`，如果同一 job 多任务并发 `_emit` 会冲突。修法：锁 `ExplorationJob FOR UPDATE`，或用数据库 sequence/唯一冲突重试。
- `server/app/services/explorer.py:106`：注册操作只按 `tenant_id + op_key` 查 existing，不处理版本升级；已有 disabled/pending 会阻止新版本产生。修法：按 `(tenant, op_key, version)` 管理版本，active 用部分唯一约束限制单 active。
- `server/app/main.py:15`：`allow_credentials=True` 与可配置 origins 组合，如果环境把 `cors_origins=*` 会变成危险/无效配置。修法：启动时拒绝 `*` + credentials；生产只允许精确 origin。
- `server/app/config.py:11`、`server/app/config.py:13`：默认 secret/db 账号是 dev 值，未按 `app_env` 强制生产覆盖。修法：`app_env != dev` 时校验 `secret_key/database_url/llm_api_key/cors_origins` 必须安全配置。
- `server/app/models/chat.py:28`：`ChatMessage.created_at` 是 `String`，其他表是 timezone-aware `DateTime`；排序和时区语义不一致。修法：改为 `DateTime(timezone=True)` 并迁移旧数据。
- `src/api/http.ts:31`、`src/App.tsx:41`：API 401 时不清 token；App 显示 Login，但 localStorage 仍保留坏 token，其他请求还会带旧 Authorization。修法：在 fetch wrapper 遇到 401 调 `setToken(null)`、`queryClient.clear()` 并触发重新渲染。
- `src/features/sources.ts:14`、`src/screens/Live.tsx:14`：Explore 页启动探索后只 toast，不把 `job_id` 传给 Live；Live 页也不会自动接上已有 running job。修法：把 current job 放全局状态/URL，或查询最近 running job 并订阅。
- `src/features/sources.ts:16`：探索开始就 invalidate operations，但实际操作在后台完成后才注册；SSE done 后没有再次 invalidate。修法：收到 `done`/`op` 事件时 invalidate `operations/sources/job`。
- `src/screens/Chat.tsx:69`、`src/features/chat.ts:28`：发送消息不检查 `sessionId`，会请求 `/chat/sessions/undefined/messages`。修法：`doSend` 在 `!sessionId` 时禁用/等待 ensure 成功；mutation `enabled` 或显式参数化 sessionId。
- `src/screens/Chat.tsx:37`、`src/screens/Chat.tsx:129`：ChatMain 和 ChatAside 各自维护 session 选择状态，可能展示不同会话的计划详情。修法：把 `sessionId` 提升到共享 context 或路由参数。
- `src/features/approvals.ts:6`：审批 hooks 存在但没有任何屏幕使用；用户无法完成 dual/confirm 审批，只能点 Chat 的确认。修法：增加审批队列 UI，或把待审批状态嵌入 Chat 并调用 vote API。

**Low**
- `server/app/api/identity.py:48`：logout 先执行了一次未使用的 `select(Session)`，且 revoke 当前用户全部 session；不是安全漏洞但行为粗糙。修法：只 revoke 当前 bearer token，提供“退出所有设备”单独接口；可定期清理 revoked/expired session。
- `server/app/api/sources.py:67`：`int(request.headers.get("last-event-id"...))` 对非法 header 会 500。修法：捕获 `ValueError`，返回 400 或重置为 0。
- `server/app/services/llm.py:51`：每次 LLM 请求新建 `httpx.AsyncClient`，高并发下连接复用差。修法：应用生命周期内复用 client，并在 shutdown 关闭。
- `server/app/api/plugins.py:18`：插件列表对所有登录用户返回 `code_signature`/实现健康信息，可能泄露内部插件结构。修法：非 admin 仅返回必要展示字段。
- `server/app/api/sources.py:27`：数据源列表返回 `conn`，可能包含连接串/路径信息。修法：后端返回 masked display name，真实连接信息只给 admin。
- `src/screens/Audit.tsx:76`：前端对任意 ok execution 显示 rollback 按钮，没有按角色隐藏；虽然后端会拦，但 UX 会误导 customer。修法：按 `acting_role` 控制按钮可见性。
- `src/screens/Flow.tsx:49`：FlowAside 用 `useApp().traceSel`，而 FlowMain 内部可能用 fallback trace；初始未设置时侧栏可能空。修法：复用同一个 `useActiveTrace()`。
- `src/api/queryClient.ts:6`：默认 `retry: 1` 会对部分非幂等感知不足的查询错误重试；影响较小。修法：按 status 区分，401/403 不 retry。

**架构隐患**
- 当前 CaMeL 关键链路“P-LLM 计划 → query 执行 → Q-LLM 隔离解析 → 策略带能力标签校验 → write 执行”没有真正串起来；主流程只生成计划和空参写执行。
- 策略引擎只有内存 Python 规则，`policy_ref` 没有动态绑定/版本化/审计执行结果；Operation Registry 的权限条件也没有统一解释器。
- 审批流 API 存在，但 UI 未接入；dual approval 在当前 seed 下不可完成，确认按钮与审批投票语义混在一起。
- 后台探索应从进程内 task 升级为持久任务队列，否则部署扩缩容/重启会造成状态永久不一致。
- 缺少覆盖 IDOR、并发 confirm、审计链并发 append、审批并发投票、SSE 鉴权、401 token 清理的测试；现有测试主要是纯逻辑 happy path。
