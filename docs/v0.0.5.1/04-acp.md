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

| 借鉴 | 应用 |
|---|---|
| tmux session = window | sessionId ↔ window 1:1 |
| capture-pane + send-keys | Hook(on_output) + prompt 注入 |
| --daemon | zchat-acp headless 运行 |
| worktree | 外化到 spawn pre_spawn |

### 2.2 来自 Xuanwo/acp-claude-code

**来源**：[github.com/Xuanwo/acp-claude-code](https://github.com/Xuanwo/acp-claude-code) — 237 stars, 归档。另见 [Zed Official ACP](https://github.com/zed-industries/claude-agent-acp)。

| 借鉴 | 应用 |
|---|---|
| ACP JSON-RPC 格式 | DataType(AcpPayload) |
| Capability negotiation | initialize Message |
| Permission mode | Annotation(injection_path) |

### 2.3 来自 Claude-to-IM

**来源**：[github.com/op7418/Claude-to-IM](https://github.com/op7418/Claude-to-IM)。

| 借鉴 | 应用 |
|---|---|
| 输出事件分类 | Hook(on_output) |
| canUseTool 阻塞 | Hook(pre_tool_use) |
| Session lock | Access control |

### 2.4 来自 ACP 生态

**来源**：[ACP spec](https://github.com/agentclientprotocol/agent-client-protocol)、[zed.dev/acp](https://zed.dev/acp)。

| 借鉴 | 应用 |
|---|---|
| session/set_mode | Access mode 切换 |

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
