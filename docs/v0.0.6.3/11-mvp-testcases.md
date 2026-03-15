# MVP 测试用例 v0.0.6.3

---

## E2E 故事（30 Core 场景）

A(4) · B(5) · C(5) · D(6) · E(5) · G-alt(3) · H(2)

Extension 场景（未计入 Core）：F(9, ext-migrate) · G(11, ext-offline)

详见 [E2E](./08-e2e-scenarios.md)。

---

## 底层测试

### zchat-protocol（8 个）

| ID | 原语 | 说明 |
|---|---|---|
| T-P.1 | ContentType(AcpPayload) | JSON-RPC round-trip |
| T-P.2 | ContentType(AcpPayload) | error 构造 |
| T-P.3 | Index | pattern 构造器 |
| T-P.4 | Message / ZChatEvent | round-trip（含 content_type + ref 字段） |
| T-P.5 | Identity | `user@network` 解析 |
| T-P.6 | Identity | `user:agent@network` 解析 |
| T-P.7 | View | schema round-trip（含 filter/sort/group/fold） |
| T-P.8 | ExtensionManifest | manifest TOML 解析 + 验证 |

### zchat-com（16 个）

| ID | 模块 | 说明 |
|---|---|---|
| T-C.1 | identity | gh auth 解析 |
| T-C.2 | identity | `user@network` / `user:agent@network` 格式 |
| T-C.3 | network | 网络创建 + Zenoh 广播 |
| T-C.4 | network | Zenoh scout 发现 + 加入 |
| T-C.5 | room | 创建 + 自动加入 |
| T-C.6 | room | invite + SystemEvent(join) 广播 |
| T-C.7 | room | leave + SystemEvent(leave) 广播 |
| T-C.8 | event_router | ZChatEvent 路由到 Room 订阅者 |
| T-C.9 | event_router | 宽容路由：未知 content_type 正常存储 + 透传 |
| T-C.10 | event_router | 未知 content_type → 推断 ext.{name} → 提示安装 |
| T-C.11 | annotation | per-recipient priority（@mention → CRITICAL, 其他 → NORMAL） |
| T-C.12 | annotation | injection_path（AFK → jsonl） |
| T-C.13 | event_store | JSONL 写入 + 读取 + 按 content_type 查询 |
| T-C.14 | event_store | queryable backfill（peer 拉取历史 events） |
| T-C.15 | presence | 心跳 + offline 检测 + SystemEvent(offline) |
| T-C.16 | config | SpawnConfig inherits 解析：agent TOML → template TOML → 默认值 |

### zchat-acp（18 个）

| ID | 模块 | 说明 |
|---|---|---|
| T-A.1 | headless adapter | CC headless 启动（--input-format stream-json --output-format stream-json） |
| T-A.2 | headless adapter | JSONL stdin 注入 user message |
| T-A.3 | headless adapter | JSONL stdout 解析（assistant/text → ZChatEvent type=msg） |
| T-A.4 | headless adapter | JSONL stdout 解析（assistant/tool_use → ZChatEvent type=tool_use） |
| T-A.5 | headless adapter | JSONL stdout 解析（thinking → ZChatEvent type=thinking） |
| T-A.6 | headless adapter | result event → presence=idle |
| T-A.7 | enriched message | [zchat] 格式构造（room/from/mention/members/your_identity） |
| T-A.8 | enriched message | 上下文窗口：N=10 条限制 |
| T-A.9 | enriched message | 上下文窗口：T=12h 限制（不足 10 条时取 12h 内全部） |
| T-A.10 | enriched message | replyTo 引用递归展开（不计入 N 限额） |
| T-A.11 | ask bridge | CC 原生 AskUserQuestion → 转为 ask event → 收到 answer → JSONL stdin tool_result |
| T-A.12 | spawn | 4-phase 流程（workspace 准备 + CC headless 启动） |
| T-A.13 | workspace | MCP 热加载：从 config → 写入 .mcp.json |
| T-A.14 | workspace | Skills symlink：扫描 skillsDir → symlink |
| T-A.15 | pool | idle 回收：10 分钟无消息 → terminate（保留 sessionId） |
| T-A.16 | pool | resume：新消息到达 → --resume 恢复 |
| T-A.17 | attach/detach | attach → terminate headless + 输出 session ID |
| T-A.18 | attach/detach | detach → --resume 恢复 + 回扫 attach 期间消息 |

### zchat-cli（16 个）

| ID | 说明 |
|---|---|
| T-L.1 | ComBackend Protocol：MockComBackend 满足所有方法签名 |
| T-L.2 | AcpBackend Protocol：MockAcpBackend 满足所有方法签名 |
| T-L.3 | `zchat spawn ppt-maker` → 通过 AcpBackend.prepare_spawn + confirm_spawn |
| T-L.4 | `zchat spawn --template coder --name x` → 临时 agent |
| T-L.5 | `zchat send @ppt-maker "hello"` → 通过 ComBackend.publish |
| T-L.6 | `zchat send #room "hello"` → Room 广播 |
| T-L.7 | `zchat rooms` → 通过 ComBackend.rooms |
| T-L.8 | `zchat members #room` → 通过 ComBackend.members |
| T-L.9 | `zchat status` → peers + sessions 信息 |
| T-L.10 | `zchat doctor` → 通过 ComBackend.doctor |
| T-L.11 | `zchat watch #room` → 通过 ComBackend.subscribe 实时流式输出 |
| T-L.12 | `zchat watch #room --last 50 --no-follow` → 通过 ComBackend.query_events |
| T-L.13 | `zchat watch --verbose` → 显示 tool_use/tool_result |
| T-L.14 | `zchat ask @alice "?"` → 通过 ComBackend.publish + subscribe 阻塞等待 |
| T-L.15 | `zchat answer "ok"` → 匹配 pending ask + publish |
| T-L.16 | `zchat session attach/detach` → 通过 AcpBackend.attach/detach |

### Extension 机制（6 个）

| ID | 说明 |
|---|---|
| T-X.1 | `zchat ext install` → pip install + manifest 解析 + registry 增量更新 |
| T-X.2 | `zchat ext uninstall` → registry 注销 + pip uninstall |
| T-X.3 | `zchat ext list` → 列出已安装 extension |
| T-X.4 | 热加载：新 extension 的 Hook 立即对新 event 生效 |
| T-X.5 | 回扫：热加载后自动处理近期 Event Store 中匹配的未处理 event |
| T-X.6 | CLI 子命令动态注册：extension 安装后其 CLI 命令可用 |

### zchat-tui — 推迟

> 以下测试在 TUI 实现时启用。

| ID | 说明 |
|---|---|
| T-3.1 | Textual headless 渲染 |
| T-3.2 | :spawn → cli.spawn() |
| T-3.3 | Session Tab 输出 |
| T-3.4 | 命令→CLI 映射 |
| T-3.5 | 对话框显示 |
| T-3.6 | AskUserQuestion 交互式表单渲染 |
| T-3.7 | Agent 模式指示器 (Direct/AFK 状态显示) |
| T-3.8 | thinking panel 渲染 |

---

## 统计

| 类别 | v0.0.5.2 | v0.0.6.3 | 变更 |
|---|---|---|---|
| E2E 场景 | 52 | 30 (Core) | -22（迁移/离线移入 extension） |
| protocol | 10 | 8 | -2 |
| com | 26 | 16 | -10（移除 store/offline 相关） |
| acp | 26 | 18 | -8（移除 tmux/migrate 相关） |
| cli | 12 | 16 | +4（新增 Backend Protocol + watch/ask/doctor） |
| extension | 0 | 6 | 新增 |
| tui | 8 | 0 (推迟) | -8 |
| **底层合计** | **82** | **64** | -18 |
| **总计** | **134** | **94** | -40 |

---

## 测试基础设施

| 关注点 | 方案 |
|---|---|
| Zenoh 隔离 | `multicast.enabled=false` + 显式 endpoints |
| 多用户 | 多 Zenoh session（不同 Identity） |
| CC headless mock | MockClaudeProcess（模拟 JSONL 协议） |
| 测试 agent | echo script（非 Claude Code） |
| Extension 测试 | 测试用 mock extension（注册 test.* content_type） |
| 热加载测试 | 运行时 install mock extension → 验证 registry 更新 + 回扫 |

### Phase 3 测试标准

- 生产代码中 0 个 mock 模块
- 测试中仅 fixtures（数据）是构造的
- 所有 API 调用是真实的（真实 Zenoh + 真实 CC headless）
- 不允许 `@mock.patch` 掉整个模块

---

## 相关文档

- [架构概览](./01-overview.md) · [E2E](./08-e2e-scenarios.md) · [开发阶段](./09-dev-phases.md)
- [protocol](./03-protocol.md) · [com](./04-com.md) · [acp](./05-acp.md) · [cli](./02-cli.md)
- [MVP 实现](./10-mvp-implementation.md) · [Extension 机制](./06-extension.md)
