# zchat-acp 设计文档 v0.0.5.1
## Agent 侧通信接口

---

## 1. 概览

zchat-acp 面向 **Agent** 的控制层。核心原语：Hook 的注册与调度。当前仅支持 Claude Code（tmux backend）。

```
              zchat-protocol
             /              \
        zchat-com       → zchat-acp ←
             \              /
          zchat-cli
```

| 对比 | zchat-com | zchat-acp |
|---|---|---|
| 面向 | 人类 | Agent (Claude Code) |
| 核心 | Message 路由 + Annotation | Hook 调度 + Access |
| 角色 | Message 路由者 | ACP Index 的订阅者/发布者 |

---

## 2. Where to Steal

### 2.1 来自 Claude Squad

**来源**：[github.com/smtg-ai/claude-squad](https://github.com/smtg-ai/claude-squad) — 6k+ stars。另见[官网](https://smtg-ai.github.io/claude-squad/)。

**与 zchat 的关系**：Claude Squad 是单机多 Agent 并行管理器——在一台机器上用 tmux 隔离多个 CC 实例。zchat-acp 的 tmux backend 直接对标其核心架构，但将管理范围从"单机多 Agent"扩展到"局域网多人多 Agent"。Claude Squad 解决了 tmux 层的工程难题，zchat 可以复用其方案，专注于网络层和协作层。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| tmux session 1:1 映射 | sessionId ↔ window 1:1 | 每个 Agent 独占一个 tmux session，生命周期清晰，避免多 Agent 共享 session 的复杂性 |
| PTY 直连 + capture-pane 轮询 | Hook(on_output) + prompt 注入 | 通过 PTY 写入原始字节，比 `tmux send-keys` 更可靠；capture-pane 100ms 轮询 + SHA-256 变化检测实现输出监听 |
| 正则匹配检测 Agent 状态 | OutputParser 状态分类 | 通过匹配 CC 的已知 prompt 模式（如权限请求文本）判断 Agent 是否空闲/等待输入——简单但脆弱，zchat 需要 fallback 策略 |
| daemon 模式（TUI/daemon 互斥） | zchat-acp headless 运行 | TUI 退出时 fork 独立 daemon 进程自动应答，zchat 类似但需支持网络事件，不能仅做 auto-accept |
| worktree 隔离 | 外化到 spawn pre_spawn | 每个 Agent 独立 git worktree，避免并发 Agent 在同一工作目录冲突 |

**注意差异**：Claude Squad 硬编码 10 实例上限，无并发安全（多 TUI 实例共享状态文件会冲突），diff 基于创建时 HEAD（主分支前进后 diff 膨胀）。zchat 需规避这些问题。

### 2.2 来自 Xuanwo/acp-claude-code

**来源**：[github.com/Xuanwo/acp-claude-code](https://github.com/Xuanwo/acp-claude-code) — 237 stars, 归档。另见 [Zed Official ACP](https://github.com/zed-industries/claude-agent-acp)。

**与 zchat 的关系**：acp-claude-code 是最早将 Claude Code 接入 ACP 协议的桥接器（存活约一周后被 Zed 官方实现取代）。zchat 的 DataType(AcpPayload) 需要理解 ACP JSON-RPC 的格式约定，而 Zed 官方实现展示了生产级的 capability 协商和权限流。两者合在一起提供了 ACP 适配的完整参考。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| stdio JSON-RPC 传输 | DataType(AcpPayload) 格式 | ACP 以 stdin/stdout 换行分隔 JSON-RPC 为默认传输，zchat 的 AcpPayload 需要遵守此格式以保持兼容性 |
| Capability 协商（initialize 握手） | initialize Message | 客户端和 Agent 在连接时交换能力集（如 loadSession、image、audio），zchat spawn 时同样需要协商 Agent 支持的能力 |
| Permission mode 分级 | Annotation(injection_path) | 从 default → acceptEdits → bypassPermissions 分级控制，Zed 官方版进一步引入 canUseTool 回调实现交互式授权——zchat 的 Access 模型可参考此分级 |
| 长生命周期 session（Pushable 模式） | session resume | Zed 官方版用异步可迭代流保持 CC 进程跨 prompt 存活，避免每次 prompt 重建 query——zchat 的 session 也需要持久化 |

**注意差异**：Xuanwo 版每次 prompt 创建新 query（靠 resume 恢复），Zed 版用 Pushable 流保持单一 query。zchat 通过 tmux session 天然持久化，不需要模仿 Pushable 模式，但 resume 逻辑值得参考。

### 2.3 来自 Claude-to-IM

**来源**：[github.com/op7418/Claude-to-IM](https://github.com/op7418/Claude-to-IM)。从 [CodePilot](https://github.com/op7418/CodePilot) 提取的独立库。

**与 zchat 的关系**：Claude-to-IM 将 Claude Code 的输出桥接到 IM 平台（Telegram/Discord/飞书/QQ），核心解决"如何分类 Agent 输出事件"和"如何在 Agent 执行过程中阻塞等待人类授权"两个问题。zchat-acp 的 Hook(on_output) 和 Hook(pre_tool_use) 面对完全相同的问题，但 zchat 走 Zenoh P2P 而非 IM HTTP API。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| SSE 事件分类（text/tool_use/permission_request/status） | Hook(on_output) 事件类型 | 将 CC 的流式输出分类为文本块、工具调用、权限请求、状态变更——zchat 的 OutputParser 需要同样的分类逻辑 |
| previewText 与 currentText 分离 | OutputParser 聚合策略 | currentText 在 tool_use 时重置，previewText 只增不减——保证流式预览连续性。zchat 向 Room 广播时同样需要区分"当前块"和"完整回合" |
| canUseTool 阻塞式权限流 | Hook(pre_tool_use) | CC SDK 的 canUseTool 回调是 async 阻塞的——返回 Promise 前工具不执行。zchat 通过 Zenoh 转发权限请求给 Operator，同样需要阻塞-等待-超时机制 |
| Promise chain session lock | Access control 串行化 | 同一 session 的消息通过 Promise chain 串行处理，不同 session 并发——防止竞态。zchat 的 Access guard 需要同样的 per-session 串行保证 |
| DI 四接口解耦（Store/LLM/Permission/Lifecycle） | zchat-acp interface 抽象 | 将持久化、LLM 调用、权限解析、生命周期钩子拆为独立接口——zchat 的 Backend 抽象（当前仅 tmux）可借鉴此解耦模式 |

**注意差异**：Claude-to-IM 的权限超时是 5 分钟硬编码。zchat 的 Operator 可能不在线，需要更灵活的超时策略（如 AFK 自动降级）。

### 2.4 来自 ACP 生态

**来源**：[ACP spec](https://github.com/agentclientprotocol/agent-client-protocol)、[zed.dev/acp](https://zed.dev/acp)。2.3k+ stars，由 Zed + JetBrains 共同维护。

**与 zchat 的关系**：ACP 是 AI Agent 与编辑器之间的标准协议（"Agent 界的 LSP"）。zchat 的 ACP 扩展方法（`_zchat.dev/*`）构建在 ACP 规范之上。理解 ACP 的设计哲学有助于让 zchat 的扩展与生态兼容。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| session/set_mode + Config Options | Access mode 切换 | ACP 正从固定 mode 枚举迁移到通用 Config Options（key-value 选择器），zchat 的 mode 设计应跟随此趋势以保持兼容 |
| Capability 协商 + 单整数版本号 | initialize 握手 | 通过能力集而非版本号驱动功能发现——新功能加 capability 而不升大版本，zchat 可复用此模式实现渐进式功能扩展 |
| Permission request（allow_once/always/reject） | Access 权限语义 | ACP 定义了四种权限响应语义，zchat 的 Owner/Operator/Observer 可映射到这些语义上 |
| `_` 前缀扩展方法 | `_zchat.dev/*` 方法命名 | ACP 保留无前缀方法给标准协议，`_` 前缀用于自定义扩展——zchat 已遵循此约定 |
| MCP-over-ACP（RFD 草案） | 未来 MCP 集成路径 | 允许通过 ACP 通道路由 MCP 工具调用，免去独立 MCP server 进程——zchat 可关注此 RFD 的进展 |

**注意**：ACP 当前 30+ Agent 实现（含 Claude、Copilot、Gemini CLI、Codex CLI），5 语言 SDK。zchat 的 `_zchat.dev/*` 扩展在协议层合规，但应关注 session/resume 和 Proxy Chains RFD 的进展——后者可能影响 zchat 的迁移机制设计。

---

## 3. Hook：事件驱动的 Agent 控制

Hook 是 zchat-acp 的核心。所有 Agent 行为——输出捕获、房间同步、迁移打包、权限检查——都通过 Hook 实现。

### 3.1 注册与调度

全局 Hook registry。session 创建时加载 SpawnConfig + system hooks，按 trigger 分组、priority 排序。事件发生时依次执行。

### 3.2 runtime="zchat" 的 Hook

在 zchat-acp 进程内执行。

| trigger | handler | 用途 |
|---|---|---|
| `on_output` | `zchat://output_classify` | OutputParser: capture-pane → 分类 → 发布到 Room Index |
| `on_route` | `zchat://inject_decision` | 读 Annotation(injection_path) → send-keys 或 queue |
| `on_idle` | `zchat://end_turn` | idle → resolve pending prompt |
| `on_migrate_out` | `zchat://bundle_pack` | 打包 MigrationBundle |
| `on_migrate_in` | `zchat://bundle_restore` | 接收 → spawn + resume |

### 3.3 runtime="agent" 的 Hook

在 CC 进程内执行。handler 是 **shell command**，调用 zchat CLI。

| trigger | shell command | 用途 |
|---|---|---|
| `session_end` | `zchat bundle-return {session_id}` | /exit 时打包回传 |
| `after_prompt` | `zchat status {session_id} --check-reclaim` | reclaim 后提示脱网 |
| `pre_tool_use` | `./check-preToolUse.sh`（用户自定义） | tool 前检查 |

**CLI 而非 MCP**：CLI 不依赖 CC 的 MCP 机制，任何能执行 bash 的环境都可以。无需额外 MCP server 进程。

### 3.4 zchat_inject：Hook 安装器

Spawn Phase 2 读取 runtime="agent" 的 Hook → 翻译为 CC hook 脚本 → 安装。

```bash
# 生成 ~/.claude/hooks/session-end.sh:
#!/bin/bash
zchat bundle-return "$ZCHAT_SESSION_ID"
```

system hook 强制安装。user hook 由 SpawnConfig 配置。同 trigger 合并为一个脚本按 priority 执行。

---

## 4. tmux Backend（Claude Code）

```
Zenoh (Message on ACP Index)
         │
  ┌──────▼──────┐
  │  server.py   │ Message → Hook 调度
  └──────┬───────┘
         │
  ┌──────▼──────────────┐
  │  tmux backend        │
  │  ├ bridge.py         │ send_keys + capture_pane
  │  ├ output_parser.py  │ Hook(on_output): 终端→Message→Room
  │  ├ access.py         │ access guard
  │  └ agents/cc.py      │ CC patterns + zchat_inject 配置
  └──────────────────────┘
```

**OutputParser 是唯一脆弱组件**——fallback 为 `agent_message_chunk`，系统永不崩溃。

**agents/cc.py** 提供 CC 特有的 patterns（permission regex、spinner 检测、idle 判定）。

---

## 5. Spawn：Agent 生命周期

### 5.1 四阶段

```
Phase 1: pre_spawn    ← 用户脚本（worktree, deps）
Phase 2: zchat_inject ← 自动: 安装 runtime="agent" Hook（不可覆盖）
Phase 3: launch       ← 自动: tmux new-window + CC 启动
Phase 4: post_spawn   ← 用户脚本
```

### 5.2 配置分层：Template + Agent

角色模板和 Agent 实例分开存放：

```
.zchat/
├── templates/         ← 角色模板（"工程师"）
│   └── coder.toml
└── agents/            ← Agent 实例（"张三"）
    └── ppt-maker.toml
```

**Template 示例** (`.zchat/templates/coder.toml`):

```toml
[meta]
program = "claude"

[skills]
enabled = ["superpowers", "skill-creator"]

[mcp_servers]
extra = ["context7"]

[hooks]
pre_tool_use = { handler = "./check-preToolUse.sh", runtime = "agent" }

[pre_spawn]
script = "git worktree add ..."
```

**Agent 实例示例** (`.zchat/agents/ppt-maker.toml`):

```toml
inherits = "coder"          # ← 继承 templates/coder.toml

[meta]
name = "ppt-maker"          # 覆盖名称

[skills]
enabled = ["superpowers", "skill-creator", "pptx-skill"]  # 覆盖
```

**解析顺序**：agent TOML → inherits 的 template TOML → 内置默认值。显式字段覆盖。

`skills` 和 `mcp_servers.extra` 是 CC 内部配置，zchat 原样传递。

### 5.3 --resume

从 inbox/ 中的 SessionEndBundle 恢复：pre_spawn(apply diff) → zchat_inject → launch + CC /resume → post_spawn(rejoin rooms)。

---

## 6. Access：权限模型

### 6.1 三角色

| 角色 | 权限 |
|---|---|
| **Owner** | grant、reclaim、kill |
| **Operator** | 独占交互、AFK；不能 grant 或 kill |
| **Observer** | 只读 |

### 6.2 grant = 物理迁移

```
alice: :session grant alice:ppt-maker bob

1. 广播 SystemEvent(migrating)
2. 等 idle → Hook(on_migrate_out): 打包 MigrationBundle
3. Zenoh 传输 → bob
4. bob Hook(on_migrate_in): spawn + resume + queryable 补回
5. alice: kill CC + 释放 Index
6. 广播 SystemEvent(migrated)
```

规则：只有 Owner 能 grant；Owner 必须是当前 Operator；Identity 和 Index 不变。

### 6.3 reclaim = 收回网络身份

```
alice: :session reclaim alice:ppt-maker

1. 发布 ReclaimNotify
2. bob 侧: 取消订阅 ACP Index + 从 Room 移除 + 注入 Hook(after_prompt) 脱网提示
3. alice 重新拥有身份
4. bob CC 继续本地运行（脱网）
5. bob /exit → Hook(session_end) → bundle 经 outbox/relay 回传
```

### 6.4 关闭安全

Owner 本地 /exit：检查 Agent 所在 Room 的其他人类成员 → 有 → TUI 确认。Operator /exit：不阻止，Hook(session_end) 自动回传 bundle。

---

## 7. CC → Room 同步

OutputParser 捕获用户输入（send-keys 后文本变化）→ Message 发布到 Room Index。agent 回复聚合 → end_turn 后发布。Agent 所在房间列表存于 session metadata。

---

## 8. ACP 协议映射

### 标准方法

| Method | 实现 |
|---|---|
| initialize | 返回 capabilities |
| session/new | spawn lifecycle → tmux window |
| session/prompt | access check → send-keys |
| session/cancel | send-keys Escape |

### 扩展 (`_zchat.dev/*`)

| Method | 用途 |
|---|---|
| access/set_mode, get_mode | mode 切换 |
| session/attach | 订阅 update（只读） |
| session/grant | 触发迁移 |
| session/reclaim | 收回身份 |
| spawn/list | 列出模板 |
| sessions/list | 列出 session |

---

## 9. 模块清单

| 模块 | 职责 |
|---|---|
| server.py | Zenoh subscriber + Hook 调度 |
| interface.py | Backend 抽象（当前仅 tmux） |
| spawn.py | 4-phase + Hook 注册 + zchat_inject + --resume |
| access.py | Owner/Operator/Observer + mode |
| migrate.py | grant/reclaim/SessionEnd |
| tmux/bridge.py | libtmux send_keys + capture_pane |
| tmux/output_parser.py | Hook(on_output) 实现 |
| tmux/access.py | tmux access guard |
| tmux/agents/cc.py | CC patterns |

---

## 10. 边界

| 范围内 | 范围外 |
|---|---|
| Hook 注册 + 调度 | Message 路由 (com) |
| tmux backend (CC) | Annotation 附加 (com) |
| Spawn + resume | Timeline / store (com) |
| Access + migrate | TUI (tui) |
| zchat_inject | CLI 子命令实现 (cli) |

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-protocol](./02-protocol.md) · [zchat-com](./03-com.md) · [zchat-cli](./05-cli.md) · [zchat-tui](./06-tui.md)
- [开发阶段](./08-dev-phases.md) · [E2E](./07-e2e-scenarios.md) · [MVP](./09-mvp-implementation.md) · [测试](./10-mvp-testcases.md)
