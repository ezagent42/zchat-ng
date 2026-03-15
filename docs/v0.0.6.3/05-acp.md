# zchat-acp 设计文档 v0.0.6.3
## 适配实现：implements AcpBackend

---

## 1. 概览

zchat-acp **实现 zchat-cli 定义的 AcpBackend 接口**——将各参与方（人类、CC、Gemini CLI、自定义 agent）的异构本地操作翻译为标准格式（ZChat Operation）。

```
    zchat-cli（核心层：定义 AcpBackend Protocol）
        │
        ▼
    zchat-protocol（数据层）
        ▲
 → zchat-acp ←（implements AcpBackend）
```

zchat-acp 不 import zchat-cli。它依赖 zchat-protocol 的类型定义，并实现 cli 中定义的 AcpBackend Protocol。

**命名澄清 (v0.0.5.2)**：
- **ZChat Operation**：zchat 环境的通用操作格式（`msg`/`thinking`/`tool_use`/`ask`/...）。这是 zchat 自身的概念。
- **AcpPayload**：ACP Adapter 的内部序列化格式——当 agent 支持 ACP 协议时，adapter 将 ACP JSON-RPC 翻译为 ZChat Operation。它只是众多 adapter 格式之一。
- **zchat-acp 包名**：沿用"acp"是因为该包的核心职责是 agent 通信协议的适配（Agent Communication Protocol 的广义含义），但 ZChat Operation 本身不绑定任何特定外部协议。

```
    zchat-cli（核心层）
        │
    zchat-protocol（数据层）
        ▲
    zchat-com        → zchat-acp ←
  (ComBackend)       (AcpBackend)
```

| 对比 | zchat-com (ComBackend) | zchat-acp (AcpBackend) |
|---|---|---|
| 实现 | ComBackend Protocol | AcpBackend Protocol |
| 解决 | HOW：ZChatEvent 如何传输和路由 | WHAT：Agent 如何适配 + 操作标准化 |
| 核心 | Zenoh pub/sub + Event Store + 宽容路由 | CC Headless Adapter + enriched message + 进程池 |

### 1.1 AFK Mode 为默认 *(v0.0.6 变更)*

Agent 以 headless 子进程运行（CC 使用 `--input-format stream-json`），无 TUI。AFK Mode 是确定性的、可测试的、且对 agent-to-agent 场景更友好。

Direct Mode（tmux 集成）推迟实现。人类需要直接交互时使用 attach/detach 机制。

### 1.2 对称性：无固定 Editor/Agent 角色

ZChat Operation 没有 "request"/"response" type。协议层只有 Participant 和 Operation。

- 人类在 CLI 发消息 → ZChat Operation `{type: "msg", from: "alice"}`
- CC 回复 → ZChat Operation `{type: "msg", from: "alice:ppt-maker"}`
- CC 主动 @bob → CC tool_use: `zchat send @bob "..."` → Zenoh publish

所有方向的消息用同一种格式，Turn 从 `replyTo` 链涌现。

### 1.3 CC ↔ ZChat 交互：模型 1+2 共存 *(new in v0.0.6)*

**模型 2（被动/默认）**：
- Room event → adapter 构造 enriched message → JSONL stdin → CC
- CC stdout → adapter 解析 → 自动路由回源 Room

**模型 1（主动/可选）**：
- CC 通过 AgentSkill 学会 zchat CLI
- CC tool_use: `Bash("zchat send/ask/watch ...")` → CLI 进程 → Zenoh publish
- Zenoh 本身就是 IPC，不需要额外机制

模型 2 保证基本功能不依赖 CC 的 skill 水平。模型 1 解锁高级协作能力（跨 Room、查询、ask）。

---

## 2. Where to Steal

### 2.1 来自 Claude Squad

**来源**：[github.com/smtg-ai/claude-squad](https://github.com/smtg-ai/claude-squad) — 6k+ stars。另见[官网](https://smtg-ai.github.io/claude-squad/)。

**与 zchat 的关系**：Claude Squad 是单机多 Agent 并行管理器——在一台机器上用 tmux 隔离多个 CC 实例。zchat-acp 的进程池管理直接对标其核心架构，但将管理范围从"单机多 Agent"扩展到"局域网多人多 Agent"。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| tmux session 1:1 映射 | sessionId ↔ CC headless 进程 1:1 | 每个 Agent 独占一个 session，生命周期清晰 |
| 正则匹配检测 Agent 状态 | CC headless JSONL result event 检测 idle | JSONL 协议比正则匹配更可靠 |
| daemon 模式 | zchat 长驻进程 + headless CC | zchat 类似但需支持网络事件 |
| worktree 隔离 | 外化到 spawn pre_spawn | 每个 Agent 独立 git worktree，避免并发冲突 |

**注意差异**：Claude Squad 硬编码 10 实例上限，无并发安全（多 TUI 实例共享状态文件会冲突），diff 基于创建时 HEAD。zchat 需规避这些问题。

### 2.2 来自 Xuanwo/acp-claude-code

**来源**：[github.com/Xuanwo/acp-claude-code](https://github.com/Xuanwo/acp-claude-code) — 237 stars, 归档。另见 [Zed Official ACP](https://github.com/zed-industries/claude-agent-acp)。

**与 zchat 的关系**：acp-claude-code 是最早将 Claude Code 接入 ACP 协议的桥接器。zchat 的 ContentType(AcpPayload) 需要理解 ACP JSON-RPC 的格式约定，而 Zed 官方实现展示了生产级的 capability 协商和权限流。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| stdio JSON-RPC 传输 | ContentType(AcpPayload) 格式 | ACP 以 stdin/stdout 换行分隔 JSON-RPC 为默认传输 |
| Capability 协商（initialize 握手） | initialize Message | 客户端和 Agent 在连接时交换能力集 |
| Permission mode 分级 | Access 权限语义 | 从 default → acceptEdits → bypassPermissions 分级控制 |
| 长生命周期 session（Pushable 模式） | session resume | Zed 官方版用异步可迭代流保持 CC 进程跨 prompt 存活 |

**注意差异**：zchat 通过 CC headless 进程 + `--resume` 天然持久化 session。

### 2.3 来自 Claude-to-IM

**来源**：[github.com/op7418/Claude-to-IM](https://github.com/op7418/Claude-to-IM)。从 [CodePilot](https://github.com/op7418/CodePilot) 提取的独立库。

**与 zchat 的关系**：Claude-to-IM 将 Claude Code 的输出桥接到 IM 平台。zchat-acp 的 enriched message 构造和 CC stdout 分类面对相同的问题。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| SSE 事件分类（text/tool_use/permission_request/status） | CC stdout JSONL 分类 | 将 CC 输出分类为文本块、工具调用、权限请求、状态变更 |
| previewText 与 currentText 分离 | CC stdout 全量广播 + watch 过滤 | zchat 将所有 CC 输出广播到 Room，由 watch 过滤显示 |
| canUseTool 阻塞式权限流 | ask/answer 机制 | CC 的权限请求转为 ask event，人类 answer 后继续 |
| Promise chain session lock | per-session 串行保证 | 同一 session 消息串行处理 |
| DI 四接口解耦 | Adapter 接口抽象 | 将持久化、LLM 调用、权限解析、生命周期拆为独立接口 |

**注意差异**：Claude-to-IM 的权限超时是 5 分钟硬编码。zchat ask 超时默认 30 分钟，可配置。

### 2.4 来自 ACP 生态

**来源**：[ACP spec](https://github.com/agentclientprotocol/agent-client-protocol)、[zed.dev/acp](https://zed.dev/acp)。2.3k+ stars，由 Zed + JetBrains 共同维护。

**与 zchat 的关系**：ACP 是 AI Agent 与编辑器之间的标准协议。zchat 的 ACP 扩展方法（`_zchat.dev/*`）构建在 ACP 规范之上。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| session/set_mode + Config Options | Access mode 切换 | ACP 正从固定 mode 枚举迁移到通用 Config Options |
| Capability 协商 + 单整数版本号 | initialize 握手 | 通过能力集而非版本号驱动功能发现 |
| Permission request（allow_once/always/reject） | Access 权限语义 | ACP 定义了四种权限响应语义 |
| `_` 前缀扩展方法 | `_zchat.dev/*` 方法命名 | ACP 保留无前缀方法给标准协议 |
| MCP-over-ACP（RFD 草案） | 未来 MCP 集成路径 | 允许通过 ACP 通道路由 MCP 工具调用 |

**注意**：ACP 当前 30+ Agent 实现，5 语言 SDK。zchat 应关注 session/resume 和 Proxy Chains RFD 进展。

---

## 3. Hook：事件驱动的 Agent 控制

Hook 是 zchat-acp 的核心。Agent 行为——输出广播、房间同步、权限检查——都通过 Hook 实现。

### 3.1 注册与调度

全局 Hook registry（与 Extension Registry 共享）。session 创建时加载 SpawnConfig + system hooks，按 trigger 分组、priority 排序。事件发生时依次执行。

### 3.2 runtime="zchat" 的 Hook

在 zchat-acp 进程内执行。

| trigger | handler | 用途 | v0.0.6.3 状态 |
|---|---|---|---|
| `on_output` | `zchat://output_classify` | OutputParser: capture-pane → 分类 → 发布到 Room | 推迟 (Direct Mode) |
| `on_route` | `zchat://inject_decision` | 读 Annotation(injection_path) → enriched message 注入 | Core |
| `on_idle` | `zchat://end_turn` | idle → resolve pending prompt | Core |
| `on_migrate_out` | `zchat://bundle_pack` | 打包 MigrationBundle | → ext-migrate |
| `on_migrate_in` | `zchat://bundle_restore` | 接收 → spawn + resume | → ext-migrate |

### 3.3 runtime="agent" 的 Hook

在 CC 进程内执行。handler 是 **shell command**，调用 zchat CLI。

| trigger | shell command | 用途 |
|---|---|---|
| `session_end` | `zchat session-end {session_id}` | 进程退出时清理 |
| `after_prompt` | `zchat status {session_id}` | prompt 后状态检查 |
| `pre_tool_use` | `./check-preToolUse.sh`（用户自定义） | tool 前检查 |

**CLI 而非 MCP**：CLI 不依赖 CC 的 MCP 机制，任何能执行 bash 的环境都可以。无需额外 MCP server 进程。

### 3.4 zchat_inject：Hook 安装器

Spawn Phase 2 读取 runtime="agent" 的 Hook → 翻译为 CC hook 脚本 → 安装。

system hook 强制安装。user hook 由 SpawnConfig 配置。同 trigger 合并为一个脚本按 priority 执行。

---

## 4. CC Headless Adapter（AFK Mode）

> 吸收自 [NeoClaw](https://github.com/amszuidas/neoclaw) 项目的 `ClaudeCodeAgent` 实现。

AFK 模式下，CC 以 headless 子进程运行，通过双向 JSONL streaming protocol 通信：

```
ZChat Operation (from zchat-com)
         │
  ┌──────▼──────────────────┐
  │  CC Headless Adapter      │
  │  ├ process.py             │ ClaudeProcess: Bun.spawn + Mutex + JSONL I/O
  │  ├ pool.py                │ 进程池: Map<convId, {process, sessionId, lastActive}>
  │  ├ translator.py          │ ZChat Operation ↔ JSONL 双向翻译
  │  ├ enriched_message.py    │ 上下文窗口构造 (new in v0.0.6)
  │  └ ask_bridge.py          │ AskUserQuestion 桥接
  └──────┬──────────────────┘
         │ stdin: {"type":"user","message":{...}}
         │ stdout: system/init | assistant | result
  ┌──────▼──────┐
  │  claude CLI  │  --input-format stream-json --output-format stream-json
  │  (headless)  │  --resume <sessionId> --model claude-sonnet-4-6
  └──────────────┘
```

### CC 启动参数

```bash
claude --input-format stream-json \
       --output-format stream-json \
       --verbose \
       --model <config.agent.model> \
       --resume <sessionId> \                    # 恢复之前的 session
       --dangerously-skip-permissions \          # 或 --allowedTools 白名单
       --append-system-prompt "..."              # 注入自定义 system prompt
```

### JSONL 协议

**stdin → CC (发送)**:
```json
{"type":"user","message":{"role":"user","content":"你好"}}
{"type":"user","message":{"role":"user","content":[
  {"type":"text","text":"这张图是什么？"},
  {"type":"image","source":{"type":"base64","media_type":"image/png","data":"..."}}
]}}
```

**stdout ← CC (接收)**:
```json
{"type":"system","subtype":"init","session_id":"...","model":"..."}
{"type":"assistant","message":{"role":"assistant","content":[
  {"type":"text","text":"你好！"},
  {"type":"tool_use","id":"...","name":"Bash","input":{"command":"ls"}}
]}}
{"type":"result","result":"完成","session_id":"...","cost_usd":0.05,"duration_ms":3200}
```

### ZChat Operation ↔ JSONL 翻译

| 方向 | ZChat Operation | JSONL |
|---|---|---|
| inbound `msg` | `{type:"msg", content:"..."}` | stdin `{"type":"user","message":{"role":"user","content":"..."}}` |
| inbound `msg` (enriched) | `{type:"msg"}` + 上下文窗口 | stdin `{"type":"user","message":{"role":"user","content":"[zchat] room=... \n---\n..."}}` |
| inbound `answer` | `{type:"answer", text:"..."}` | stdin（格式化为 user message，包含原 ask 上下文） |
| outbound `msg` | `{type:"msg", from:"alice:ppt-maker"}` | stdout `assistant.content[{type:"text"}]` |
| outbound `thinking` | `{type:"thinking"}` | stdout `assistant.content[{type:"thinking"}]` |
| outbound `tool_use` | `{type:"tool_use", tool, input}` | stdout `assistant.content[{type:"tool_use"}]` |
| outbound `tool_result` | `{type:"tool_result"}` | stdout `result` event 中的隐含工具结果 |
| outbound `ask` | `{type:"ask", question:"..."}` | stdout `result.permission_denials` 中提取 AskUserQuestion |

### AskUserQuestion 桥接细节

CC 调用 AskUserQuestion → permission deny → adapter 从 `result.permission_denials` 提取问题 → 构造 ZChatEvent `{type:"ask", from:"alice:ppt-maker"}` → zchat-com publish 到 Room → 人类 `zchat answer` → adapter 收到 answer event → 格式化为 JSONL stdin user message 注入 CC。

无需 system prompt hint hack——ACP 协议层没有固定角色，agent 主动提问只是一条普通 Operation。

### 4.1 Enriched Message 构造 *(new in v0.0.6)*

当 CC 被 @mention 时，adapter 构造 enriched message 注入 CC stdin：

```
[zchat] room=#workshop from=alice mention=true
members: alice, bob, @ppt-maker, @data-cruncher
your_identity: alice:ppt-maker
--- recent context (5 messages) ---
[10:30] alice: Q3 数据跑出来了吗
[10:32] bob: charlie 在跑，应该快了
[10:35] alice: 等数据出来后 PPT 要更新
[10:40] charlie: 修好了，实际下降 8%
[10:45] alice: @ppt-maker 用新数据更新 PPT
---
```

**上下文窗口规则**：
- 触发条件：CC 被 @mention 时注入
- 窗口大小：最近 10 条 OR 12 小时内全部，取条数较少者
- 引用展开：窗口内消息如有 replyTo，递归包含被引用消息，不计入 10 条限额
- 非 @mention 消息：只存储在 Event Store 中，不注入 CC context
- CC 主动扩展：CC 可通过 AgentSkill 调用 `zchat watch --last N --no-follow` 获取更多上下文

**批量注入**：CC idle 期间若积累多条 @mention 消息，合并为一条 enriched message（包含所有触发消息 + 上下文窗口）。

### 4.2 CC stdout 全量广播 *(new in v0.0.6)*

CC stdout 的所有输出类型全部广播到 Room：

| CC stdout type | ZChatEvent type | 说明 |
|---|---|---|
| assistant/text | msg | 文本回复 |
| assistant/tool_use | tool_use | 工具调用 |
| assistant/thinking | thinking | thinking stream |
| tool_result | tool_result | 工具返回结果 |
| result | → presence=idle | 标记 CC idle，不广播内容 |

过滤是 `zchat watch` 显示层的事：
- 默认：显示 msg + ask + answer + system-event
- `--verbose`：+ tool_use + tool_result
- `--thinking`：+ thinking
- `--all`：不过滤

### 4.3 CC 原生 AskUserQuestion 处理 *(new in v0.0.6)*

CC headless 的 JSONL protocol 中有原生 ask_user_question 机制。Adapter 拦截后：
1. 转换为 ZChatEvent(type=ask) 发到 Room
2. Subscribe answer event（filter replyTo=ask_id）
3. 收到 answer 后通过 JSONL stdin 返回 tool_result 给 CC

与 CC 通过 `zchat ask` CLI 调用的路径殊途同归——都变成 Room 中的 ask/answer event pair。

ask 超时默认 30 分钟。超时后 CC 的 tool_use 收到错误信息，CC 自行决定下一步。

---

## 4.4 进程池

```python
pool = Map<convId, {
    process: ClaudeProcess | TmuxPaneRef | None,  # AFK: headless | Direct: tmux ref (推迟)
    sessionId: str | None,           # CC session ID for --resume
    lastActive: int,                 # idle 计时 (unix ms)
    mode: "afk" | "direct",         # 当前模式（MVP 仅支持 "afk"，Direct Mode 推迟实现时启用）
}>
```

**生命周期**：
1. spawn → 创建进程 → pool 注册
2. 消息到达 → 激活进程（如已回收则 `--resume`）
3. idle 10 分钟 → 回收进程（terminate），保留 sessionId
4. 下次消息 → `--resume <sessionId>` 恢复
5. kill → 从 pool 移除

### 4.5 attach/detach *(new in v0.0.6)*

人类需要直接与 CC 交互时的 escape hatch：

```
zchat session attach ppt-maker
  1. terminate headless 进程
  2. 标记 session 为 ATTACHED（停止注入消息）
  3. 输出 session ID + 提示命令

zchat session detach ppt-maker
  1. --resume 恢复 headless 进程
  2. 回扫 attach 期间积累的 @mention 消息
  3. 恢复正常注入流程
```

---

## 4.6 Workspace 自动化准备

> 吸收自 NeoClaw 的 `_prepareWorkspace()` 机制。

每次新 CC 子进程启动前自动执行：

```
_prepareWorkspace(conversationId):
  1. 创建 workspace 目录: ~/.zchat/workspaces/<conversationId>/
  2. MCP 热加载: 从 config 读取 mcpServers → 写入 <workspace>/.mcp.json
     - 每次读最新配置（不缓存），运行时修改立即生效
  3. Skills 同步: 扫描 skillsDir → symlink 到 <workspace>/.claude/skills/
     - 新增 skill → 创建 symlink
     - 删除 skill → 移除过时 symlink
     - 修改 SKILL.md → 通过 symlink 自动生效
```

### Adapter 接口规范

所有 adapter 实现统一接口：

```python
class ACPAdapter(Protocol):
    """每个 Participant 的 adapter"""
    async def capture_output(self) -> AsyncIterator[ZChatOperation]:
        """将本地操作转换为 ZChat Operation (outbound)"""
        ...
    async def deliver_operation(self, op: ZChatOperation) -> None:
        """将 ZChat Operation 投递到本地处理 (inbound)"""
        ...
```

---

## 5. Spawn：Agent 生命周期

### 5.1 四阶段

```
Phase 1: pre_spawn    ← 用户脚本（worktree, deps）
Phase 2: zchat_inject ← 自动: 安装 runtime="agent" Hook（不可覆盖）
Phase 3: launch       ← 自动: CC headless 启动 (AFK 默认)
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

恢复已有 session：从 pool 获取 sessionId → launch + CC `--resume` → post_spawn(rejoin rooms)。

---

## 6. Access：权限模型 *(v0.0.6.3 精简)*

### 6.1 两角色

| 角色 | 权限 |
|---|---|
| **Owner** | spawn、kill、attach/detach |
| **Operator** | 独占交互（@mention → CC 响应） |

> **v0.0.6 变更**：移除 Observer 角色（推迟）；移除 grant/reclaim（→ ext-migrate）。MVP 中 Owner = Operator。

### 6.2 grant = 物理迁移 *(→ ext-migrate)*

> 以下内容移入 ext-migrate Extension，完整设计保留供参考。

```
alice: zchat session grant alice:ppt-maker bob

1. 广播 SystemEvent(migrating)
2. 等 idle → Hook(on_migrate_out): 打包 MigrationBundle
3. Zenoh 传输 → bob
4. bob Hook(on_migrate_in): spawn + resume + queryable 补回
5. alice: kill CC + 释放 Index
6. 广播 SystemEvent(migrated)
```

规则：只有 Owner 能 grant；Owner 必须是当前 Operator；Identity 和 Index 不变。

### 6.3 reclaim = 收回网络身份 *(→ ext-migrate)*

> 以下内容移入 ext-migrate Extension，完整设计保留供参考。

```
alice: zchat session reclaim alice:ppt-maker

1. 发布 ReclaimNotify
2. bob 侧: 取消订阅 ACP Index + 从 Room 移除 + 注入 Hook(after_prompt) 脱网提示
3. alice 重新拥有身份
4. bob CC 继续本地运行（脱网）
5. bob /exit → Hook(session_end) → bundle 回传
```

### 6.4 关闭安全

Owner `zchat session kill`：检查 Agent 所在 Room 的其他人类成员 → 有 → CLI 警告需 `--force`。

---

## 7. CC → Room 同步

**v0.0.6.3**：所有 CC 输出全量广播到 Room。

**Outbound (CC → Room)**：CC headless stdout JSONL → Translator → ZChatEvent（type=msg/thinking/tool_use/tool_result）→ zchat-com publish 到 Room。

**Inbound (Room → CC)**：Room event → adapter 检查 @mention → 构造 enriched message → JSONL stdin → CC headless。

**CC 主动操作 (模型 1)**：CC tool_use `Bash("zchat send ...")` → 新 CLI 进程 → Zenoh publish。与 adapter 无关——CLI 进程直接参与 Zenoh 网络。

Agent 所在房间列表存于 session metadata。

---

## 8. ACP 协议映射

### 标准方法

| Method | 实现 |
|---|---|
| initialize | 返回 capabilities |
| session/new | spawn lifecycle → headless 启动 |
| session/prompt | enriched message → JSONL stdin |
| session/cancel | terminate headless |

### 扩展 (`_zchat.dev/*`) *(v0.0.6.3 精简)*

| Method | 用途 | v0.0.6.3 状态 |
|---|---|---|
| access/set_mode, get_mode | mode 切换 | 推迟 (无 Direct Mode) |
| session/attach | 暂停 headless + 输出 session ID | Core |
| session/detach | 恢复 headless + 回扫 | Core |
| session/grant | 触发迁移 | → ext-migrate |
| session/reclaim | 收回身份 | → ext-migrate |
| spawn/list | 列出模板 | Core |
| sessions/list | 列出 session | Core |

---

## 9. tmux Backend（Claude Code, Direct Mode）*(推迟实现)*

> **v0.0.6 变更**：整个 Direct Mode tmux 集成推迟实现。以下设计保留供未来参考。

```
Zenoh (ZChatEvent)
         │
  ┌──────▼──────┐
  │  server.py   │ Event → Hook 调度
  └──────┬───────┘
         │
  ┌──────▼──────────────┐
  │  tmux backend        │
  │  ├ bridge.py         │ send_keys + capture_pane
  │  ├ output_parser.py  │ Hook(on_output): 终端→ZChat Operation→Room
  │  ├ access.py         │ access guard
  │  └ agents/cc.py      │ CC patterns + zchat_inject 配置
  └──────────────────────┘
```

**OutputParser 是唯一脆弱组件**——fallback 为 `agent_message_chunk`，系统永不崩溃。

**agents/cc.py** 提供 CC 特有的 patterns（permission regex、spinner 检测、idle 判定）。

**Direct ↔ AFK 切换**（推迟）：
- Direct → AFK：记录 sessionId → 关闭 tmux pane → headless `--resume` spawn → adapter 切换
- AFK → Direct：获取 sessionId → terminate headless → tmux `--resume` → adapter 切换

---

## 10. 模块清单

| 模块 | 职责 | v0.0.6.3 状态 |
|---|---|---|
| server.py | Zenoh subscriber + ZChat Operation 调度 | Core |
| interface.py | Adapter 抽象接口（ACPAdapter Protocol） | Core |
| spawn.py | 4-phase + Hook 注册 + zchat_inject + --resume | Core |
| access.py | Owner/Operator | Core (精简) |
| migrate.py | grant/reclaim/SessionEnd | → ext-migrate |
| pool.py | 进程池管理（Session Map + idle 回收 + resume） | Core |
| workspace.py | Workspace 自动化准备（MCP 注入 + Skills 同步） | Core |
| headless/process.py | ClaudeProcess 子进程管理 (AFK Mode) | Core |
| headless/translator.py | ZChat Operation ↔ JSONL 翻译 | Core |
| headless/enriched_message.py | Enriched message 构造 + 上下文窗口 | Core (new) |
| headless/ask_bridge.py | AskUserQuestion 桥接 | Core |
| tmux/bridge.py | libtmux send_keys + capture_pane (Direct Mode) | 推迟 |
| tmux/output_parser.py | Hook(on_output) 实现 (Direct Mode) | 推迟 |
| tmux/access.py | tmux access guard | 推迟 |
| tmux/agents/cc.py | CC patterns | 推迟 |

---

## 11. 边界

| 范围内 | 范围外 |
|---|---|
| Hook 注册 + 调度 | Message 路由 (com) |
| CC Headless Adapter (AFK) | Annotation 附加 (com) |
| Enriched message 构造 | Event Store (com) |
| Spawn + resume | TUI (tui, 推迟) |
| Access (Owner/Operator) | 迁移 (ext-migrate) |
| zchat_inject | tmux backend (推迟) |
| 进程池 | |
| attach/detach | |

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-protocol](./03-protocol.md) · [zchat-com](./04-com.md) · [zchat-cli](./02-cli.md) · [zchat-tui](./07-tui.md)
- [Extension 机制](./06-extension.md) · [开发阶段](./09-dev-phases.md) · [E2E](./08-e2e-scenarios.md) · [MVP](./10-mvp-implementation.md) · [测试](./11-mvp-testcases.md)
