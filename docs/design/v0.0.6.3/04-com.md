# zchat-com 设计文档 v0.0.6.3
## 传输实现：implements ComBackend

---

## 1. 概览

zchat-com **实现 zchat-cli 定义的 ComBackend 接口**——一个 P2P Matrix-lite 传输层。每个节点既是 "Matrix homeserver"（存储本地事件、响应其他节点同步请求）也是 "Matrix client"（向其他节点发送事件）。

```
    zchat-cli（核心层：定义 ComBackend Protocol）
        │
        ▼
    zchat-protocol（数据层）
        ▲
 → zchat-com ←（implements ComBackend）
```

zchat-com 不 import zchat-cli。它依赖 zchat-protocol 的类型定义，并实现 cli 中定义的 ComBackend Protocol。

**核心设计哲学**：借鉴 Matrix Event Model（一切皆不可变事件、Room 为状态容器、事件 DAG 因果排序），但大幅精简——保留 ~20% 的 Matrix spec（事件模型），砍掉 ~80%（联邦 API、State Resolution v2、Auth Chain、E2EE）。传输层由 Zenoh pub/sub 替代 HTTP REST。

zchat-com **不理解 ZChat Operation 语义**——它只接收 ZChatEvent 并通过 Zenoh 路由和投递。

**宽容路由 (v0.0.6)**：zchat-com 对未知 content_type 的 ZChatEvent 做透传——结构校验通过即存储和路由，不要求 content_type 预先注册。这使 Extension 产生的新 ContentType 无需 core 预先注册即可在网络中传输。

```
    zchat-cli（核心层）
        │
    zchat-protocol（数据层）
        ▲
 → zchat-com ←        zchat-acp
  (ComBackend)       (AcpBackend)
```

**可嵌入性**：禁止 import Textual。通过 callback / async iterator 与前端通信。

### 1.1 zchat-com Daemon 架构

每台机器上运行一个 zchat-com daemon（作为 zchat 长驻进程的子模块）：

```
┌─ zchat-com (子模块) ───────────────────────────────────────┐
│                                                             │
│  Local Event Store (JSONL chunk rotation / SQLite)          │
│  ├── 存储本节点 participant 产生的 events                   │
│  └── 存储从 Zenoh 收到的其他节点 events                     │
│  └── 存储未知 content_type 的 events（宽容存储）            │
│                                                             │
│  Zenoh Session                                              │
│  ├── publish: 本地 event → zchat/room/{roomId}/**           │
│  ├── subscribe: zchat/room/{roomId}/** → 收 event           │
│  └── queryable: 响应 backfill 请求（历史事件补全）          │
│                                                             │
│  ACP Interface (进程内调用)                                  │
│  ├── adapter → com: 提交新 ZChatEvent                       │
│  └── com → adapter: 推送收到的 ZChatEvent                   │
│                                                             │
│  Extension Registry (共享)                                   │
│  ├── 宽容路由: 未知 content_type → 存储 + 透传 + 提示       │
│  └── 热加载: 新 extension 注册后立即生效                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Zenoh 天然替代 Matrix Federation API**：

| Matrix Federation 操作 | Zenoh 等价 |
|---|---|
| `make_join` + `send_join` | subscribe to `zchat/room/{roomId}/**` |
| `backfill` (历史补全) | Zenoh storage plugin 的 `get` query / queryable |
| `send_transaction` | Zenoh publish |
| Server discovery | Zenoh scouting（零配置 P2P 发现） |

### 1.2 Matrix spec 的取舍

**保留**：Immutable Event、Room=State Container、Event References (简化为单 replyTo)、Membership State、Event Type System、Redaction Model。

**砍掉**：State Resolution v2（LAN 用 last-writer-wins）、Server-Server Federation API（Zenoh 替代）、Client-Server REST API（进程内调用替代）、Event Auth Chain（LAN 互信）、PDU/EDU 区分（统一为 ephemeral 标记）、Identity Service（GitHub auth）、E2EE（DEFER）。

**演进路径**：v0.0.6.3 LAN 互信 → vNext 加 event signing → vFuture Zenoh-Matrix bridge 接入互联网。

---

## 2. Where to Steal

### 2.1 来自 Agent Teams

**来源**：[CC Agent Teams](https://code.claude.com/docs/en/agent-teams)，2026-02-05。另见 [paddo.dev](https://paddo.dev/blog/claude-code-hidden-swarm/)、[alexop.dev](https://alexop.dev/posts/from-tasks-to-swarms-agent-teams-in-claude-code/)。

**与 zchat 的关系**：Agent Teams 是 Claude Code 内置的多 Agent 协作系统——一个 session 作为 team lead 派发任务，多个 teammate session 并行执行。它使用文件系统做协调（磁盘上的 JSON 文件充当 inbox 和 task list），所有通信限于单机。zchat-com 将相同的协作模式扩展到局域网多人场景：用 Zenoh P2P 替代文件系统，用 Room 替代 team，用 Message + Annotation 替代 mailbox + task list。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| 文件系统 Inbox mailbox | Zenoh 传输的 Event Store | Agent Teams 用磁盘文件做消息投递，天然持久化且 crash-safe。zchat 用 Zenoh pub/sub + Event Store 实现同样的持久化投递，但支持跨机器 |
| P2P 消息（任意 teammate 间直接通信） | 无 leader 瓶颈的 Message 路由 | Agent Teams 允许 teammate 间直接通信，不经过 lead 中转——zchat 同样采用 P2P 路由，避免单点瓶颈 |
| Delegate mode（lead 只协调不执行） | Annotation(priority) 机制 | Delegate mode 将 lead 定位为纯调度者。zchat 通过 Annotation priority 实现类似效果：@mention 的 Agent 获得 CRITICAL 优先级，其他成员按 NORMAL 接收 |
| 自领取任务 + 依赖感知 | Room 内 Agent 自主响应 | Agent Teams 的 teammate 自动认领未被占用的 unblocked task，无需 lead 逐个分配。zchat 的 Agent 基于 Annotation priority 自主决定响应顺序，理念一致 |
| broadcast 消息（慎用，成本线性增长） | Room 广播规则 | Agent Teams 明确警告 broadcast 的 token 成本与成员数成正比。zchat 的房间广播也需要同样的设计意识——每个 Agent 成员都是一个完整 context window |

**注意差异**：Agent Teams 限于单机（文件系统协调），无固定 leadership 转让，不支持 Agent 迁移。zchat 需解决跨机器投递、离线补偿等 Agent Teams 不涉及的问题。

### 2.2 来自 Claude-to-IM

**来源**：[github.com/op7418/Claude-to-IM](https://github.com/op7418/Claude-to-IM)，MIT。从 [CodePilot](https://github.com/op7418/CodePilot) 提取。

**与 zchat 的关系**：Claude-to-IM 将 Claude Code 的消息桥接到 IM 平台（Telegram/Discord/飞书/QQ）。它的 Channel Router 解决了"如何将消息从 Agent 路由到正确的聊天频道"，Delivery Layer 解决了"如何可靠投递到可能离线的对端"——这两个问题与 zchat-com 的 Message 路由和同步机制高度同构。zchat 面对的是 Zenoh topic 而非 IM API，但路由和投递的设计模式可以复用。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| Channel Router（地址 → session 绑定） | Message 路由基于 Index | Claude-to-IM 将 IM chatId 绑定到 CC session，按绑定关系路由消息。zchat 将 Room/DM 绑定到 Index topic，思路一致但路由目标从"IM 频道"变为"Zenoh key expression" |
| 权限请求转发（流内阻塞 → IM 按钮 → 回调解除） | Message(content_type=acp.request_permission) → callback | Claude-to-IM 在消费 SSE 流时同步转发权限请求到 IM，用户点击按钮后回调解除阻塞。zchat 通过 Zenoh 将权限请求 Message 路由给 Operator，机制不同但流程同构 |
| 可靠投递（分块 + 去重 + 分类重试 + 指数退避） | ext-offline 的投递机制 | Claude-to-IM 将投递失败分为 rate_limit/server_error/network（可重试）和 client_error/parse_error（不重试）。ext-offline 需要类似的错误分类和重试策略 |
| 双层 offset 安全（fetchOffset / committedOffset） | ext-offline 的 ACK 机制 | Telegram adapter 分离"已拉取"和"已确认"两个 offset，保证 crash 后不丢消息。ext-offline 的 DeliveryConfirm 机制解决相同问题 |
| Adapter 注册表（插件式多平台） | 未来扩展模式参考 | Claude-to-IM 通过 side-effect import 自注册 adapter，添加新平台只需一个文件。zchat 当前仅支持 CC backend，但未来扩展其他 Agent 时可参考此模式 |

**注意差异**：Claude-to-IM 面对的是 IM HTTP API（有平台限制如消息长度、速率限制），zchat 面对的是 Zenoh P2P（无外部速率限制但需处理 peer 离线）。投递层的约束不同，但可靠投递的设计模式是通用的。

---

## 3. Identity：网络中的参与者

### 3.1 人类身份

`alice@onesyn`。`user` 来自 `gh auth login`，`network` 为 LAN 网络名。

### 3.2 Agent 身份

`alice:ppt-maker@onesyn`。`agent` 由用户 spawn 时命名。携带 `owner`/`operator`。

> **v0.0.6 变更**：移除 `observers` 字段（Observer 角色推迟实现）。

### 3.3 认证

首次启动引导 `gh auth login`。写入 `~/.zchat/identity.toml`。

### 3.4 网络管理

- 首用户创建网络（命名），广播到 Index(`zchat/network/announce`)
- 后续用户 Zenoh scout → 发现 → 自动加入
- 持久化到 `~/.zchat/network.toml`

---

## 4. Room：通信空间

### 4.1 CRUD

| 操作 | 行为 |
|---|---|
| create | 创建 + 创建者自动加入 |
| invite | 邀请人类或 Agent + SystemEvent |
| leave | 离开 + SystemEvent |

### 4.2 成员管理

成员列表含人类和 Agent 的 Identity。通过 Zenoh queryable 维护。

### 4.3 系统事件

join / leave / offline / online / closed → Message(content_type="application/vnd.zchat.system-event") 广播。

> **v0.0.6 变更**：移除 migrating / migrated / reclaimed 事件类型（→ ext-migrate）。

---

## 5. Message：路由与投递

### 5.1 统一模型

所有通信——团队消息、Agent 操作、系统事件——都是 ZChatEvent，属于某个 Room。zchat-com 做 Room-based event 分发，并在路由时为每个接收者附加 Annotation（构建层原语）实现 per-recipient 差异化。

### 5.2 宽容路由规则 *(v0.0.6 新增)*

ZChatEvent 产生后，zchat-com 路由流程：

1. **结构校验**：必须有 id / room / type / from / timestamp / content。结构非法 → 丢弃
2. **存储**：所有结构合法的 event 存入 Event Store，不管 content_type 是否已知
3. publish 到 `zchat/room/{roomId}/events`
4. 该 Room 的所有订阅者收到同一个 event
5. **Annotation 附加**：com 根据 `event.content.mentions[]` 和 Room 成员关系，为每个接收者附加 per-recipient Annotation
6. **未知类型提示**：如果 content_type 匹配 `ext.{name}.*` 模式且本地无对应 Extension → 向本地用户提示安装

DM = 两人 Room（创建时自动命名如 `dm:alice:bob`）。广播 = 发到全局 Room `#general`。

### 5.3 Annotation 附加（构建层原语驱动路由）

| key | 判定逻辑 |
|---|---|
| priority | `mentions[]` 中被 @mention → CRITICAL; 同 Room 其他成员 → NORMAL |
| injection_path | 查接收者 adapter 模式 → AFK: jsonl |

Annotation 在 com 路由层计算和附加，adapter 读取后决定具体行为。

### 5.4 房间广播规则

Room 内所有成员的 adapter 收到同一个 event + 各自的 Annotation。adapter 根据 Annotation 判定：
- CC adapter（AFK）：priority=CRITICAL → 注入 CC context（enriched message）；NORMAL → 不注入（Event Store 中可查）
- Human CLI：所有消息可通过 `zchat watch` 查看

---

## 6. View：投影规则与同步 *(v0.0.6: 原 Timeline)*

### 6.1 View 定义

View 是对 Room 中 Message 的投影规则。MVP 只实现 Default View。

```
Default View: filter=none, sort=ts, group=none, fold=none
→ 所有 Message 按时间平面展示
```

### 6.2 简单 queryable backfill *(v0.0.6.3 精简)*

重连后通过 Zenoh queryable 从 peer 拉取最近历史事件，merge + dedup。

不实现完整的 gap 检测与填充——交由 ext-offline Extension。

### 6.3 outbox / relay / inbox *(→ ext-offline)*

> **v0.0.6 变更**：完整的三级存储移入 ext-offline Extension。Core 仅保留简单 queryable backfill。

以下内容在 ext-offline 中实现：

```
~/.zchat/store/
├── outbox/    ← 本机产生的、目标离线的数据
├── relay/     ← 帮其他人暂存的副本
└── inbox/     ← 重连后拉取到的数据
```

由 Index 的 `retention="relay"` 驱动。写入流程：目标离线 → outbox → 广播 RelayRequest → 在线 peer 存 relay/ 副本。读取：重连 → queryable → peer 从 outbox/relay 返回 → merge + dedup → inbox。

DeliveryConfirm → 删除 outbox + relay。超时 30 天清理。

```toml
[sync]
replication = 2
cleanup_days = 30
```

---

## 7. ~~stdio Bridge~~ → 移除 *(v0.0.5.2)*

> v0.0.5.1 的 `stdio_bridge.py` 不再需要。AFK Mode 下 CC headless 的 JSONL stdin/stdout 通信由 zchat-acp 的 CC Headless Adapter 处理（不在 com 层）。com 层只负责 Zenoh pub/sub 传输 ZChatEvent。

---

## 8. 配置层级

| 层 | 路径 | Git |
|---|---|---|
| Global | `~/.zchat/` | 否 |
| Project | `~/project/.zchat/` | 是 |
| Runtime | `/tmp/zchat/` | 否 |

Project 目录结构：

```
~/project/.zchat/
├── templates/         ← 角色模板（团队共享）
│   ├── coder.toml
│   └── reviewer.toml
├── agents/            ← Agent 实例配置
│   └── ppt-maker.toml  (inherits = "coder")
├── priorities.toml    ← 优先级规则
└── network.toml       ← 网络信息（自动生成）
```

templates/ 存放可复用的角色蓝图，agents/ 存放具体 agent 实例配置。agent 通过 `inherits` 继承 template。

---

## 9. 模块清单

| 模块 | 职责 | v0.0.6.3 状态 |
|---|---|---|
| core.py | ZChatCore facade | Core |
| event_router.py | ZChatEvent 路由（Room pub/sub + 宽容路由 + Annotation 附加） | Core |
| network.py | 网络创建/发现/加入 | Core |
| room.py | Room CRUD + 成员 + SystemEvent + DM 创建 | Core |
| presence.py | 心跳 + peer 列表 + 状态 | Core |
| identity.py | gh auth + Identity | Core |
| config.py | 3 层配置 + sync | Core |
| store/event_store.py | Local Event Store (JSONL chunk / SQLite) | Core |
| store/outbox.py | 待发 | → ext-offline |
| store/relay.py | 帮存 | → ext-offline |
| store/inbox.py | 收到 | → ext-offline |
| sync.py | 简单 queryable backfill (Core) / 完整 gap 填充 (ext-offline) | 部分 Core |

---

## 10. 边界

| 范围内 | 范围外 |
|---|---|
| Identity + 认证 + 网络 | Agent 执行 / Adapter 实现 (acp) |
| Room CRUD (对齐 Matrix Room) | Hook 调度 (acp) |
| ZChatEvent 宽容路由 + Annotation 附加 | ZChat Operation 定义 (acp) |
| Event Store + 简单 backfill | 完整离线同步 (ext-offline) |
| | 迁移逻辑 (ext-migrate) |
| | TUI 渲染 (tui, 推迟) |

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-protocol](./03-protocol.md) · [zchat-acp](./05-acp.md) · [zchat-cli](./02-cli.md) · [zchat-tui](./07-tui.md)
- [Extension 机制](./06-extension.md) · [开发阶段](./09-dev-phases.md) · [E2E](./08-e2e-scenarios.md) · [MVP](./10-mvp-implementation.md) · [测试](./11-mvp-testcases.md)
