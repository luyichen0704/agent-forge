以下只报告我亲自运行并复现的问题；未复现的问题我也明确列出。

**Critical**
- **IDOR + 越权执行：customer 可确认 employee 的已审批计划并真实修改 `biz_records`**
  - 复现命令：`PYTHONPATH=. uv run python /tmp/agent_forge_runtime_probe.py`
  - 真实输出片段：`CASE9 customer_confirms_employee_plan vote 200 {'status': 'approved'} confirm 200 {'status': 'done', 'blocked': False} refund_status expedited verify {'valid': True, 'count': 9, ...}`
  - 根因：`app/api/chat.py:129` 的 `/plans/{plan_id}/confirm` 只按 `plan_id` 取计划，未校验 `ExecutionPlan.session_id` 所属用户、租户、角色/权限；`app/agents/orchestrator.py:167` 也只检查审批是否满足，不检查确认者是否是计划所有者或有权执行该写操作。
  - 修法：`confirm_plan/get_plan/cancel_plan` 必须 join `ChatSession` 校验 `tenant_id`、`user_id` 或管理员权限；确认写步骤时按当前 principal 重新跑 RBAC/policy，禁止低权限用户执行他人计划。

- **计划详情 IDOR：customer 可直接读取 employee plan**
  - 复现命令：`PYTHONPATH=. uv run python /tmp/agent_forge_runtime_probe.py`
  - 真实输出片段：`CASE4 plan_idor 200 {'id': 'aaf25945-2b86-4517-8c84-9a8fff0801d5', 'status': 'awaiting_confirm', 'required_confirm_level': 'confirm', 'trace_id': '854d4dee-21e8-403e-bd7f-dc176f6027a3'}`
  - 根因：`app/api/chat.py:119` 的 `/plans/{plan_id}` 只判断 plan 是否存在，没有校验 session/user/tenant。
  - 修法：读取 plan 时通过 `ExecutionPlan.session_id -> ChatSession` 校验归属；非管理员不可读他人计划。

- **Trace audit IDOR：customer 可读 employee trace 审计事件**
  - 复现命令：`PYTHONPATH=. uv run python /tmp/agent_forge_runtime_probe.py`
  - 真实输出片段：`CASE3 trace_idor 200 events 8 acting_role employee verify {'valid': True, 'count': 8, 'head': '9ff5b982022a0c4b073efbb3652695d660303cde6227ea98'}`
  - 根因：`app/api/traces.py:29` 的 `_owned_trace` 只校验 `tenant_id`，未限制 actor、role、trace 可见性；`app/api/traces.py:56` 直接返回完整 audit。
  - 修法：trace 读取增加访问策略：customer 只能读自己的 trace；employee/admin 按角色授权；必要时对 audit payload 做脱敏。

- **SSE 端点完全无鉴权**
  - 复现命令：`PYTHONPATH=. uv run python /tmp/agent_forge_runtime_probe.py`
  - 真实输出片段：`CASE6 sse_no_auth 200 'id: 1\r\nevent: done\r\ndata: {"probe": true}\r\n\r\nevent: close\r\ndata: {"status": "done"}\r\n\r\n'`
  - 根因：`app/api/sources.py:64` 的 `/exploration-jobs/{job_id}/events` 没有 `Depends(get_principal)`，且 `app/api/sources.py:74` 只按 `job_id` 拉事件，不校验租户/权限。
  - 修法：给 SSE 路由加认证依赖，订阅前校验 `ExplorationJob.tenant_id == p.tenant_id` 和角色权限；不存在或无权返回 404/403。

**High**
- **dual_approval 当前 seed 下形成死锁：需要 2 票但只有 1 个 admin**
  - 复现命令：`PYTHONPATH=. uv run python /tmp/agent_forge_runtime_probe.py`
  - 真实输出片段：`CASE7 dual_approval admin_count 1 vote1 200 {'status': 'pending', 'required_votes': 2, 'approve_votes': 1} vote2 409 {'detail': 'you have already voted'} confirm 200 {'status': 'awaiting_confirm', 'blocked': True}`
  - 根因：`app/agents/orchestrator.py:116` 对 `dual` 固定 `required_votes=2`；`app/models/execution.py:30` 和 `app/api/approvals.py:65` 禁止同一 approver 重复投票；但 seed 只有一个 admin：`app/seed.py:34`。
  - 修法：seed 至少创建两个 admin；或创建 approval 前检查可投票管理员数，不足时拒绝创建、降级策略或返回明确配置错误。

- **确认已审批写计划后，executor 报错但 plan 仍标记 done，审计链 valid 掩盖业务失败**
  - 复现命令：`PYTHONPATH=. uv run python /tmp/agent_forge_confirm_probe.py`
  - 真实输出片段：`CASE8 confirm_noargs before 200 {'status': 'awaiting_confirm', 'blocked': True} ... after 200 {'status': 'done', 'blocked': False} step_input_refs {} refund_status pending execs [{'status': 'error', 'error_code': 'not_found'}] verify {'valid': True, 'count': 9, ...}`
  - 根因：`app/services/planner.py:34` 的计划 schema 不包含参数；`app/agents/orchestrator.py:127` 创建 `PlanStep` 时未保存 input refs；`app/executors/base.py:56` 需要 `order_id/refund_id`，拿不到时 `not_found`；但 `app/agents/orchestrator.py:226` 无论 step error 仍 `plan.status = "done"`。
  - 修法：计划/步骤 schema 增加参数绑定或 executor 前解析参数；任何 execution error 应使 step/plan 为 `error` 或 `partial_failed`，不要返回 `blocked=False`/`done`。

- **logout 撤销同用户所有会话，而不是当前 token**
  - 复现命令：`PYTHONPATH=. uv run python /tmp/agent_forge_logout_probe.py`
  - 真实输出片段：`LOGOUT two_sessions before1 200 before2 200 logout 200 {'ok': True} after1 401 {'detail': 'invalid token'} after2 401 {'detail': 'invalid token'}`
  - 根因：`app/api/identity.py:51` 查询 `Session.user_id == p.user.id` 的所有 session 并全部 `revoked=True`。
  - 修法：`get_principal` 返回当前 session 或 token；logout 只 revoke 当前 token，另提供“退出所有设备”接口。

**Medium**
- **从仓库根目录运行 pytest 会收集 `server/pgdata` 并 PermissionError**
  - 复现命令：在 `/home/lmy/project/2605camel-business` 执行 `pytest -q`
  - 真实输出片段：`ERROR collecting server/pgdata ... PermissionError: [Errno 13] Permission denied: '/home/lmy/project/2605camel-business/server/pgdata/conftest.py'`
  - 根因：pytest 从仓库根目录运行时没有根级 pytest 配置排除 `server/pgdata`；`server/pyproject.toml` 的 `testpaths = ["tests"]` 只在 `server/` 目录下生效；`server/pgdata` 权限为 `drwx------ 19 70 root ...`。
  - 修法：在仓库根增加 `pytest.ini`/`pyproject.toml` 指定 `testpaths = server/tests` 和 `norecursedirs = server/pgdata`；或把 pgdata 移出仓库。

**Low / 已验证正常**
- `uv run pytest -q` 在 `server/` 内正常：`10 passed in 0.32s`。
- 无效 token 调 `/me` 正常返回 401：`CASE1 invalid_me 401 {'detail': 'invalid token'}`。
- 旧 token 登出后确实失效：`CASE2 logout ... after_logout 401 {'detail': 'invalid token'}`。
- `chat/sessions/:id/messages` 已校验用户归属，customer 读 employee session 返回 404：`CASE5 chat_messages_cross_user 404 {'detail': 'session not found'}`。
- 后台 explore HTTP 任务本次真实完成，没有复现异常吞掉：`CASE10 background_explore ... final {'status': 'done', 'phase': 4, 'progress': 100}`。
- 真实 LLM chat 本次未稳定生成写计划：`REAL_CHAT ... {'writes': 0, 'confirm': 'auto', 'status': 'confirmed'}`；另一次 smoke 生成写计划但未审批确认被阻塞：`confirm → status=awaiting_confirm blocked=True`。

总体结论：项目基础启动、测试和真实 LLM/后台任务可运行，但当前存在严重的 plan/trace/SSE 鉴权缺口，以及写执行状态语义错误；不建议在未修复鉴权与执行失败处理前用于真实多用户环境。
