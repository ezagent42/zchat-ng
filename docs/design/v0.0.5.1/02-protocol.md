# zchat-protocol 设计文档 v0.0.5.1
## 原语定义层

---

## 1. 概览

zchat-protocol 定义所有 8 个原语的 schema。是 zchat-com 和 zchat-acp 的唯一共享依赖。

```
           → zchat-protocol ←
             /              \
        zchat-com          zchat-acp
             \              /
          zchat-cli
```

原则：只有类型定义和常量，无业务逻辑。无非标准库运行时依赖。

---

## 2. DataType：结构化数据的基础类型声明

每个 DataType 有唯一 `type_name`、字段定义和序列化方式。DataType 只描述数据结构，不含业务逻辑。

### 2.1 TextContent

```
type_name: "text"
字段: content (str)
序列化: UTF-8 字符串
```

### 2.2 AcpPayload

ACP 协议负载，JSON-RPC 2.0 格式。覆盖：`session/new`、`session/prompt`、`session/update`、`session/cancel`、`request_permission`。

```
type_name: "acp.*"（如 "acp.session.prompt"）
字段: jsonrpc, method, params, id, result, error
序列化: JSON-RPC 2.0
```

JSON-RPC 2.0 序列化/反序列化工具（请求、响应、通知、错误的构造与解析）作为 AcpPayload 的配套提供。

参考：[ACP spec](https://github.com/agentclientprotocol/agent-client-protocol)、[agentclientprotocol.com](https://agentclientprotocol.com)、[zed.dev/acp](https://zed.dev/acp)。

### 2.3 MigrationBundle

grant 迁移时打包的完整 Agent 状态。

```
type_name: "migration_bundle"
字段:
  config:   SpawnConfig      ← spawn 配置
  history:  bytes            ← CC session JSONL
  diff:     str              ← git diff（未提交变更）
  rooms:    list[str]        ← 所在房间
  mode:     str              ← 当前 access mode
序列化: JSON 元数据 + 二进制附件
```

### 2.4 SessionEndBundle

Operator /exit 时 SessionEnd hook 打包的回传数据。

```
type_name: "session_end_bundle"
字段:
  history:  bytes            ← 更新后的 CC session JSONL
  diff:     str              ← 操作期间代码变更
```

### 2.5 SystemEvent

```
type_name: "system_event"
字段:
  event_type: str    ← "join"|"leave"|"offline"|"online"|"migrating"|"migrated"|"reclaimed"|"closed"
  subject:    Identity
  detail:     str | None
```

### 2.6 SpawnConfig

Agent 实例的完整配置。支持通过 `inherits` 继承 template。

```
type_name: "spawn_config"
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
source:     str        ← "system" | "user"
can_block:  bool       ← 能否拦截事件继续
```

### 3.2 trigger 类型

| trigger | 时机 | 典型 runtime |
|---|---|---|
| `on_output` | OutputParser 捕获终端变化 | zchat |
| `on_route` | Message 进入路由 | zchat |
| `on_idle` | Agent 空闲 (end_turn) | zchat |
| `on_migrate_out` | 发起迁移 | zchat |
| `on_migrate_in` | 接收迁移 | zchat |
| `session_end` | Agent 进程退出 | agent |
| `after_prompt` | Agent 完成 prompt 后 | agent |
| `pre_tool_use` | Agent 执行 tool 前 | agent |

### 3.3 runtime

**runtime="zchat"**：在 zchat-acp 进程内执行。handler 是内置函数标识（如 `zchat://room_sync`）。

**runtime="agent"**：在 Agent 进程内执行。handler 是 **shell command**，由 CC 原生 hook 机制触发。shell 中调用 zchat CLI 子命令。

### 3.4 system vs user

system hook 由 zchat_inject 自动安装，不可覆盖。user hook 在 SpawnConfig 中配置。同 trigger 按 priority 排序。

---

## 4. Annotation：数据上的动态元信息

```
target:  Identity      ← 给谁看
key:     str           ← "priority" | "injection_path" | "offline_gap" | "room_context"
value:   Any
stage:   str           ← "route" | "inject" | "display"
```

per-recipient：同一 Message 对不同接收者有不同 Annotation。例如 bob @alice 时，alice 收到 priority=CRITICAL（被 @mention），alice:ppt-maker 收到 priority=NORMAL（房间旁听）。

---

## 5. Index：数据的可寻址性声明

```
pattern:    str        ← Zenoh key expression
queryable:  bool       ← 可否 query（离线补回）
retention:  str        ← "none" | "memory" | "jsonl" | "relay"
ttl:        int | None
```

### 完整清单

| pattern | queryable | retention | 说明 |
|---|---|---|---|
| `zchat/broadcast` | true | relay | 全局广播 |
| `zchat/room/{name}` | true | relay | 房间消息 |
| `zchat/dm/{session_id}` | true | relay | 私信 |
| `zchat/presence` | false | none | 心跳 |
| `zchat/acp/{session}/request` | true | relay | client → agent |
| `zchat/acp/{session}/response` | false | none | agent → client |
| `zchat/acp/{session}/update` | false | memory | 流式通知 |
| `zchat/acp/_new/request` | false | none | 创建 session |
| `zchat/acp/_init/request` | false | none | 握手 |
| `zchat/acp/{session}/migrate` | true | relay | 迁移 bundle |
| `zchat/acp/{session}/history` | true | jsonl | Session 快照 |
| `zchat/sync/relay` | true | relay | relay 请求 |
| `zchat/sync/confirm` | false | none | 投递确认 |
| `zchat/network/announce` | true | memory | 网络名 |
| `zchat/network/join` | false | none | 加入通知 |

---

## 6. Identity

```
人类:  alice@onesyn  → { user, network }
Agent: alice:ppt-maker@onesyn → { user, agent, network, owner, operator, observers }
```

`user` 来自 `gh auth login`（GitHub username）。`network` 首用户创建时命名。`agent` 用户 spawn 时命名。

---

## 7. Message

```
id:            str                   ← "msg_{ts}_{random}"
ts:            str                   ← ISO 8601
sender:        Identity
target:        Target                ← { type: "dm"|"room"|"broadcast", id }
content:       DataType 实例
content_type:  str                   ← DataType 的 type_name
annotations:   list[Annotation]      ← 路由时附加
```

ACP 也是 Message（content_type="acp.*"）。stdio bridge 中 ACP 和团队消息通过 content 结构自描述区分。

---

## 8. Timeline

```
scope:         str                   ← 房间名 / DM 对
entries:       list[Message]         ← 按 ts 有序
gaps:          list[TimeGap]         ← { start_ts, end_ts, filled }
last_seen_ts:  str
```

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-com](./03-com.md) · [zchat-acp](./04-acp.md) · [zchat-cli](./05-cli.md) · [zchat-tui](./06-tui.md)
- [开发阶段](./08-dev-phases.md) · [E2E](./07-e2e-scenarios.md) · [MVP](./09-mvp-implementation.md) · [测试](./10-mvp-testcases.md)
