# Demo 模式使用指南

`VITE_DEMO=1` 时前端零后端运行，所有 HTTP/SSE 由本地脚本化 mock 提供，可完整离线演示全部 7 个屏幕。

## 快速启动

```bash
npm run demo
# 等价于：VITE_DEMO=1 vite
```

浏览器打开 http://localhost:5173，关闭后端仍可正常使用。

## 演示账号

| 邮箱 | 密码 | 角色 | 可见屏幕 |
|------|------|------|----------|
| zhang@demo.com | demo1234 | customer（客户） | Chat、Flow |
| wei@company.com | demo1234 | employee（员工） | Chat、Flow、Live、Ops |
| admin@company.com | demo1234 | admin（管理员） | 全部 7 屏 |
| admin2@company.com | demo1234 | admin（管理员乙） | 全部 7 屏（双人审批第二票） |

## 分镜操作步骤

### 分镜 1 — 项目结构（口播）
展示仓库结构：`src/` 前端、`server/` 后端、`installer/`，说明 Demo 模式下无需启动任何后端。

### 分镜 2 — 角色登录与 RBAC 差异
1. 用 `zhang@demo.com` / `demo1234` 登录
2. 展示「只能看到 Chat 和 Flow」两个屏幕 → 这是服务端 RBAC 的结果
3. 切换到 `wei@company.com` 登录 → 可见 Chat、Flow、Live、Ops

### 分镜 3–5 — 场景 A：员工执行退款加急（标准流程）

1. 以 `wei@company.com` 登录
2. 进入 Chat 屏，点击「新会话」
3. 输入：`查一下张伟的退款单，把还在 pending 的加急处理`
4. 等待 2–3s（P-LLM 规划中提示），收到 4 步计划：
   - customer.query → order.query → Q-LLM 解析 → refund.expedite
   - 计划状态：awaiting_confirm，writes=1
5. 点击「确认执行」
6. 等待约 1.5s，执行完成：
   - 回复「已规划并执行：查询张伟退款单并加急处理 pending 退款」
   - Flow 屏出现新 trace：5 节点有向图，节点带 trusted/data/parsed/write 标签

### 分镜 6 — 场景 B：双人审批（管理员）

1. 以 `admin@company.com` 登录
2. Chat 输入：`帮我设置薪资`
3. 收到计划：dual 级，blocked=true，审批请求已创建（1/2票）
4. 进入 Ops 屏 → Approvals → 看到 pending 审批
5. 以 `admin` 投一票（approve）→ 仍提示需要更多审批
6. 尝试同一账号再投票 → 弹出错误「同一审批人不能重复投票」
7. 退出，以 `admin2@company.com` 登录
8. 进入 Approvals → 投票 approve
9. 状态变为 approved，计划 done

### 分镜 7 — 数据流图（Flow 屏）

1. 打开 Flow 屏
2. 查看分镜 3–5 生成的新 trace：「张伟退款加急处理」
3. 展示 5 节点有向图：
   - n0 (trusted) → n1 (data) → n2 (data) → n3 (parsed) → n4 (write)
   - Q-LLM 输出标记为 `parsed`（不可信数据不放宽）

### 分镜 8 — 审计链（Audit 屏）

1. 以 `admin@company.com` 登录，进入 Audit 屏
2. 选中「张伟退款加急处理」trace
3. 展示 8 条事件：REQUEST_RECEIVED → PLAN_GENERATED → POLICY_EVALUATED → CONFIRMATION_REQUESTED → USER_CONFIRMED → OPERATION_EXECUTED → DATAFLOW_SNAPSHOT → RESPONSE_SENT
4. 哈希链完整性验证：verification.valid = true
5. 点击回滚按钮（rollback）演示 before/after 记录

### 分镜 9 — 探索实况（Explore → Live 屏）

1. 以 `admin@company.com` 登录，进入 Explore 屏
2. 找到「源代码 (GitHub · company/backend)」数据源
3. 点击「开始探索」→ 自动跳转 Live 屏
4. 观察 SSE 实时事件流：
   - Phase 1：全局认知 — 扫描 ts/py 文件
   - Phase 2：深度探索 — 提取 Order/RefundRecord/Customer 实体
   - Phase 3：操作生成 — 生成 3 个新操作草稿
   - Phase 4：能力标注 — 标注完成
   - 总时长约 15s，进度条从 0→100%
5. 探索完成后：
   - Ops 屏出现 3 个新 pending 草稿 + 2 个 active 查询操作
   - 源代码状态变为 connected

## 技术说明

- Demo 模式使用 `DemoAdapter` 拦截所有 `fetch` 请求（`src/api/http.ts` 唯一 fetch 出口）
- SSE 使用 `DemoEventSource` 替换 `window.EventSource`，只拦截 `/exploration-jobs/.+/events` URL
- 正常模式（`npm run dev`）零影响，demo 代码完全 code-split 不打入主包
- 所有延迟拟真：GET 150–350ms，发送消息 2.2–2.9s，确认 1.4–1.8s，投票 800ms
