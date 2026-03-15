# zchat-protocol 设计文档 v0.0.6.3
## 原语定义层

---

## 1. 概览

zchat-protocol 是 **zchat-cli 需求的形式化**——cli 的操作涉及 Message、Room、Identity、View 等概念，protocol 将它们声明为类型。protocol 不是「底层基石」，而是「cli 语义的数据化表达」。

```
    zchat-cli（核心层：操作定义）
        │ 依赖类型定义
        ▼
 → zchat-protocol ←（数据层：类型声明）
        ▲           ▲
    zchat-com    zchat-acp（Backend 实现）
```

原则：只有类型定义和常量，无业务逻辑。无非标准库运行时依赖。被 zchat-cli、zchat-com、zchat-acp 共同依赖。

---

## 2. ContentType：消息内容的 schema 声明 *(v0.0.6.3: 原 DataType)*

> **v0.0.6.3 变更**：原语 DataType 重命名为 ContentType。每个 ContentType 有 `short`（人类用）和 `mime`（wire format）两个标识。ZChatEvent.content_type 字段存 MIME 格式。CLI / manifest / AgentSkill 中用 short name，自动映射。

ContentType 的角色类似于 HTTP 的 Content-Type——它告诉接收方如何解释 event.content 的内容。zchat 采用标准 MIME 格式作为 wire format，同时提供简短的别名供人类交互。

### 2.0 Short ↔ MIME 映射规则

每个 ContentType 有两个标识符：

```
short name:   人类友好的简短标识，用于 CLI、manifest、AgentSkill、debug
MIME:         标准 MIME 格式，用于 ZChatEvent.content_type 字段（wire format）
```

映射规则（确定性可推导，不需要查表）：

```
规则 1:  标准 MIME 类型直接使用
  short: text/plain           →  mime: text/plain
  short: image/png            →  mime: image/png

规则 2:  zchat 自定义类型使用 vnd.zchat 前缀
  short: acp.session.prompt   →  mime: application/vnd.zchat.acp.session-prompt
  short: system-event         →  mime: application/vnd.zchat.system-event
  short: spawn-config         →  mime: application/vnd.zchat.spawn-config

规则 3:  Extension 类型使用 vnd.zchat-ext 前缀
  short: ext.migrate.migration-bundle
    →  mime: application/vnd.zchat-ext.migrate.migration-bundle

转换细节:
  short → MIME:
    标准 MIME (含 /) → 原样
    其他 → "application/vnd.zchat." + short（dot → dot, underscore → hyphen）
    ext.* → "application/vnd.zchat-ext." + rest
  
  MIME → short:
    text/* / image/* / audio/* / video/* → 原样
    application/vnd.zchat.* → 去前缀
    application/vnd.zchat-ext.* → "ext." + rest
```

CLI 和 manifest 始终使用 short name。ZChatEvent wire format 始终使用 MIME。转换由 protocol 层的工具函数自动完成。

### 2.1 TextContent

```
short: text/plain
mime:  text/plain
字段:  content (str)
序列化: UTF-8 字符串
```

### 2.2 AcpPayload

ACP 协议负载，JSON-RPC 2.0 格式。覆盖：`session/new`、`session/prompt`、`session/update`、`session/cancel`、`request_permission`。

```
short: acp.*（如 acp.session.prompt）
mime:  application/vnd.zchat.acp.*（如 application/vnd.zchat.acp.session-prompt）
字段:  jsonrpc, method, params, id, result, error
序列化: JSON-RPC 2.0
```

JSON-RPC 2.0 序列化/反序列化工具作为 AcpPayload 的配套提供。

参考：[ACP spec](https://github.com/agentclientprotocol/agent-client-protocol)、[agentclientprotocol.com](https://agentclientprotocol.com)、[zed.dev/acp](https://zed.dev/acp)。

### 2.3 MigrationBundle *(→ ext-migrate Extension)*

> **v0.0.6 变更**：此 ContentType 移入 ext-migrate Extension。

grant 迁移时打包的完整 Agent 状态。

```
short: ext.migrate.migration-bundle
mime:  application/vnd.zchat-ext.migrate.migration-bundle
字段:
  config:   SpawnConfig      ← spawn 配置
  history:  bytes            ← CC session JSONL
  diff:     str              ← git diff（未提交变更）
  rooms:    list[str]        ← 所在房间
  mode:     str              ← 当前 access mode
序列化: JSON 元数据 + 二进制附件
```

### 2.4 SessionEndBundle *(→ ext-migrate Extension)*

> **v0.0.6 变更**：此 ContentType 移入 ext-migrate Extension。标识符改为 `ext.migrate.session-end-bundle`。schema 定义保留在此供参考。

Operator /exit 时 SessionEnd hook 打包的回传数据。

```
short: ext.migrate.session-end-bundle
mime:  application/vnd.zchat-ext.migrate.session-end-bundle
字段:
  history:  bytes            ← 更新后的 CC session JSONL
  diff:     str              ← 操作期间代码变更
```

### 2.5 SystemEvent

```
short: system-event
mime:  application/vnd.zchat.system-event
字段:
  event_type: str    ← "join"|"leave"|"offline"|"online"|"closed"
  subject:    Identity
  detail:     str | None
```

> **v0.0.6 变更**：移除 "migrating"|"migrated"|"reclaimed" event_type（→ ext-migrate）。

### 2.6 SpawnConfig

Agent 实例的完整配置。支持通过 `inherits` 继承 template。

```
short: spawn-config
mime:  application/vnd.zchat.spawn-config
字段:
  inherits:    str | None    ← 继承的 template 名（如 "coder"）
  meta:        { program: str, name: str }
  hooks:       list[HookDef]
  skills:      list[str]     ← CC skills（zchat 不解释）
  mcp_servers: list[str]     ← 用户自定义额外 MCP
  pre_spawn:   str | None
  post_spawn:  str | None
序列化: TOML（磁盘）/ JSON（网络）
```

解析顺序：agent TOML（`.zchat/agents/`）→ inherits 指向的 template TOML（`.zchat/templates/`）→ 内置默认值。agent 中显式写的字段覆盖 template。

---

## 3. Hook：事件上的可执行操作

### 3.1 定义

```
trigger:    str        ← 触发点
handler:    str        ← shell command 或内置函数标识
runtime:    str        ← "zchat" | "agent"
priority:   int        ← 执行顺序（小先）
source:     str        ← "system" | "user" | "extension"
can_block:  bool       ← 能否拦截事件继续
```

> **v0.0.6 变更**：source 新增 "extension" 值，标识由 Extension 注册的 Hook。

### 3.2 trigger 类型

| trigger | 时机 | 典型 runtime | v0.0.6.3 状态 |
|---|---|---|---|
| `on_output` | OutputParser 捕获终端变化 | zchat | 推迟 (Direct Mode) |
| `on_route` | Message 进入路由 | zchat | Core |
| `on_idle` | Agent 空闲 (end_turn) | zchat | Core |
| `on_migrate_out` | 发起迁移 | zchat | → ext-migrate |
| `on_migrate_in` | 接收迁移 | zchat | → ext-migrate |
| `session_end` | Agent 进程退出 | agent | Core |
| `after_prompt` | Agent 完成 prompt 后 | agent | Core |
| `pre_tool_use` | Agent 执行 tool 前 | agent | Core |

Extension 可通过 manifest 注册新的 trigger 类型。

### 3.3 runtime

**runtime="zchat"**：在 zchat-acp 进程内执行。handler 是内置函数标识（如 `zchat://room_sync`）或 Extension 的 Python callable（如 `migrate:bundle_pack`）。

**runtime="agent"**：在 Agent 进程内执行。handler 是 **shell command**，由 CC 原生 hook 机制触发。shell 中调用 zchat CLI 子命令。

### 3.4 system vs user vs extension

system hook 由 zchat_inject 自动安装，不可覆盖。user hook 在 SpawnConfig 中配置。extension hook 由 Extension manifest 声明。同 trigger 按 priority 排序。

---

## 4. Annotation：数据上的动态元信息

Annotation 是构建层原语，用于实现通信层中 per-recipient 差异化逻辑。zchat-com 在路由 Message 时附加 Annotation。

```
target:  Identity      ← 给谁看
key:     str           ← "priority" | "injection_path" | ...
value:   Any
stage:   str           ← "route" | "inject" | "display"
```

per-recipient：同一 Message 对不同接收者有不同 Annotation。例如 bob @alice 时，alice 收到 priority=CRITICAL（被 @mention），alice:ppt-maker 收到 priority=NORMAL（房间旁听）。

**v0.0.6.3 MVP Annotation keys**：

| key | 说明 | stage |
|---|---|---|
| priority | CRITICAL（被 @mention）/ NORMAL | route |
| injection_path | afk（JSONL stdin）| inject |

Extension 可通过 manifest 注册新的 Annotation key（如 ext-offline 注册 `offline_gap`）。

**Annotation 附加逻辑**：Annotation 在 zchat-com 路由层执行——com 根据 event.content 中的 `mentions[]` 字段和 Room 成员关系，为每个接收者的 adapter 附加不同的 Annotation。adapter 读取 Annotation 后决定具体行为（AFK Mode: JSONL stdin 注入 enriched message；未来 Direct Mode: Hook additionalContext inject；未来 Human TUI: 渲染高亮）。

---

## 5. Index：数据的可寻址性声明

```
pattern:    str        ← Zenoh key expression
queryable:  bool       ← 可否 query（离线补回）
retention:  str        ← "none" | "memory" | "jsonl"
ttl:        int | None
```

> **v0.0.6 变更**：移除 `retention="relay"`（→ ext-offline）。

### 通信类 Index（对齐 Matrix Room Event）

| pattern | queryable | retention | 说明 |
|---|---|---|---|
| `zchat/room/{roomId}/events` | true | jsonl | Room 事件（消息、系统事件） |
| `zchat/room/{roomId}/state` | true | jsonl | Room 状态（成员、名称等） |
| `zchat/room/{roomId}/ephemeral` | false | none | typing, read receipt |
| `zchat/presence` | false | none | 全局心跳 |

### 运维类 Index（zchat 特有）

| pattern | queryable | retention | 说明 | v0.0.6.3 状态 |
|---|---|---|---|---|
| `zchat/acp/{session}/migrate` | true | jsonl | 迁移 bundle | → ext-migrate |
| `zchat/acp/{session}/history` | true | jsonl | Session 快照 | → ext-migrate |
| `zchat/sync/relay` | true | jsonl | relay 请求 | → ext-offline |
| `zchat/sync/confirm` | false | none | 投递确认 | → ext-offline |
| `zchat/network/announce` | true | memory | 网络名 | Core |
| `zchat/network/join` | false | none | 加入通知 | Core |

Extension 可通过 manifest 注册新的 Index pattern。

**Index 演进历史**：v0.0.5.1 → v0.0.5.2 砍掉 `zchat/dm/{session_id}`（DM = Room）、`zchat/broadcast`（广播 = 全局 Room）、`zchat/acp/{session}/request|response|update`（agent 通信走 Room event，不走独立 ACP 通道）、`zchat/acp/_new|_init/*`（初始化走 spawn 流程）。v0.0.6 进一步将迁移和离线同步的 Index 移入对应 Extension。

---

## 6. Identity

```
人类:  alice@onesyn  → { user, network }
Agent: alice:ppt-maker@onesyn → { user, agent, network, owner, operator }
```

`user` 来自 `gh auth login`（GitHub username）。`network` 首用户创建时命名。`agent` 用户 spawn 时命名。

### 6.1 Identity 与 Label

- `alice` 是一个 **Identity**，`human`（隐含）和 `ppt-maker`/`reviewer` 是她的 **labels**
- Room membership 是 Identity 级别的——alice 加入 Room 后，她的所有 labels 自动获得消息
- @mention 可以指定 label：`@alice:ppt-maker`（特定 agent）或 `@alice`（alice 本人所有端）
- 同一条消息在 alice 的不同 adapter 上都渲染，通过 event ID 去重

---

## 7. Message

```
id:            str                   ← "msg_{ts}_{random}"
ts:            str                   ← ISO 8601
sender:        Identity
target:        Target                ← { type: "dm"|"room"|"broadcast", id }
content:       ContentType 实例
content_type:  str                   ← ContentType 的 MIME 标识符（wire format）
annotations:   list[Annotation]      ← 路由时附加
```

ACP 也是 Message（content_type="application/vnd.zchat.acp.*"）。

---

## 7.1 ZChatEvent（精简版 Matrix PDU）

ZChatEvent 是 zchat-com 传输层的基本单元，借鉴 Matrix Event Model 的设计哲学（一切皆不可变事件），但大幅精简（保留 ~20% Matrix spec，去掉联邦、签名、auth chain 等复杂度）。

```
id:            str              ← ULID（内含时间排序）
room:          str              ← room identifier
type:          str              ← ZChat Operation type
from:          str              ← participant ref (account:label 或 account)
timestamp:     int              ← origin timestamp (ms)
content:       Any              ← type_specific payload

replyTo:       str | None       ← 引用的上一条 event ID（因果链）
thread:        str | None       ← thread root event ID
ephemeral:     bool             ← true = 不持久化 (typing, presence)
redacts:       str | None       ← 撤回目标 event ID

# v0.0.6 新增
ref:           str | None       ← 影射 Message 指向的目标 event ID（Socialware 预留）

# 预留，暂不实现
signatures:    dict | None      ← 未来 WAN 场景的 event 签名
auth_events:   list[str] | None ← 未来认证链
```

> **v0.0.6 变更**：新增 `ref` 字段，为 Socialware 影射 Message 预留。影射 Message 通过 ref 指向被影射的原消息。

**与 Message 的关系**：Message 是 zchat-protocol 层面的抽象；ZChatEvent 是 zchat-com 传输层面的序列化格式。Message 打包为 ZChatEvent 后由 Zenoh 传输。

---

## 7.2 ZChat Operation 类型体系

ACP 定义所有参与方可执行的操作的统一格式（WHAT），不涉及传输（HOW）。这是 zchat 自身的概念，不是 ACP 协议的概念。

```
# 消息类
msg            ← 文本/多模态消息
typing         ← 正在输入 (ephemeral)

# Agent 特有（超越 IM 的部分）
thinking       ← thinking stream
tool_use       ← agent 调用工具
tool_result    ← 工具返回结果
ask            ← AskUserQuestion（向任意 participant 提问）
answer         ← 回答 ask

# 生命周期
join           ← 加入 Room
leave          ← 离开 Room
presence       ← online/idle/afk/offline (ephemeral)

# 元操作
annotate       ← reaction / annotation
redact         ← 撤回
read           ← 已读回执 (ephemeral)

# Agent Card
discover       ← 请求 Agent Card
card           ← 返回 Agent Card
```

### v0.0.6.3 MVP 实现范围

| Operation | MVP 实现 | 说明 |
|---|---|---|
| msg | ✅ | |
| thinking | ✅ | CC stdout 全量广播 |
| tool_use | ✅ | CC stdout 全量广播 |
| tool_result | ✅ | CC stdout 全量广播 |
| ask | ✅ | zchat ask / CC 原生 AskUserQuestion |
| answer | ✅ | zchat answer |
| join | ✅ | |
| leave | ✅ | |
| presence | ✅ | |
| typing | ⬜ | 推迟 |
| read | ⬜ | 推迟 |
| annotate | ⬜ | 推迟 |
| redact | ⬜ | 推迟 |
| discover | ⬜ | 推迟 |
| card | ⬜ | 推迟 |

**对称性**：ZChat Operation 没有 "request"/"response" type。消息就是消息，`from` 字段标识发起方，`replyTo` 构成因果链。Turn 方向从 replyTo DAG 中涌现。

---

## 8. View *(v0.0.6: 原 Timeline)*

> **v0.0.6 变更**：Timeline 重命名为 View。View 是对 Room 中 Message 的投影规则，而非暗示独立存在的完整时间序列。

```
scope:         str                   ← 房间名 / DM 对
filter:        Expression | None     ← 过滤条件（None = 不过滤）
sort:          str                   ← 排序方式（默认 "ts"）
group:         str | None            ← 分组方式（None = 不分组）
fold:          str | None            ← 折叠方式（None = 平面展示, "ref" = 影射折叠到原消息下）

entries:       list[Message]         ← 按 sort 有序
gaps:          list[TimeGap]         ← { start_ts, end_ts, filled }
last_seen_ts:  str
```

**Default View**：`filter=none, sort=ts, group=none, fold=none`——所有 Message 按时间平面展示。等价于原 Timeline。

`filter`、`group`、`fold` 字段为 Socialware 预留。MVP 只实现 Default View。

---

## 9. ExtensionManifest *(new in v0.0.6)*

Extension 的声明式定义格式。详见 [Extension 机制](./06-extension.md)。

```
name:           str
version:        str
description:    str
requires_core:  str              ← 最低 core 版本

content_types:      list[ContentTypeDef]      ← 注册新的 content_type
hooks:          list[HookDef]          ← 注册新的 Hook trigger + handler
indexes:        list[IndexDef]         ← 注册新的 Zenoh key-expression
annotations:    list[str]              ← 声明新的 Annotation key
operations:     list[str]              ← 声明新的 Operation type
cli_subcommands: list[CliSubcommandDef] ← 注册新的 CLI 子命令
dependencies:   list[str]              ← 依赖的其他 Extension（扁平列表）
```

序列化：TOML（`extension.toml`）。

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-com](./04-com.md) · [zchat-acp](./05-acp.md) · [zchat-cli](./02-cli.md) · [zchat-tui](./07-tui.md)
- [Extension 机制](./06-extension.md) · [开发阶段](./09-dev-phases.md) · [E2E](./08-e2e-scenarios.md) · [MVP](./10-mvp-implementation.md) · [测试](./11-mvp-testcases.md)
