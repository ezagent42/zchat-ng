# zchat-com 设计文档 v0.0.5.1
## 人类侧通信接口

---

## 1. 概览

zchat-com 面向**人类**的通信抽象——无 UI 的 Python 库。实现通信层四个原语的运行时逻辑，使用构建层原语驱动路由和同步。

```
              zchat-protocol
             /              \
     → zchat-com ←        zchat-acp
             \              /
          zchat-cli          ← zchat-tui 通过 cli 间接使用
```

**可嵌入性**：禁止 import Textual。通过 callback / async iterator 与前端通信。

---

## 2. Where to Steal

### 2.1 来自 Agent Teams

**来源**：[CC Agent Teams](https://code.claude.com/docs/en/agent-teams)，2026-02-05。另见 [paddo.dev](https://paddo.dev/blog/claude-code-hidden-swarm/)、[alexop.dev](https://alexop.dev/posts/from-tasks-to-swarms-agent-teams-in-claude-code/)。

**与 zchat 的关系**：Agent Teams 是 Claude Code 内置的多 Agent 协作系统——一个 session 作为 team lead 派发任务，多个 teammate session 并行执行。它使用文件系统做协调（磁盘上的 JSON 文件充当 inbox 和 task list），所有通信限于单机。zchat-com 将相同的协作模式扩展到局域网多人场景：用 Zenoh P2P 替代文件系统，用 Room 替代 team，用 Message + Annotation 替代 mailbox + task list。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| 文件系统 Inbox mailbox | Zenoh 传输的 inbox（Index retention=relay） | Agent Teams 用磁盘文件做消息投递，天然持久化且 crash-safe。zchat 用 Zenoh pub/sub + outbox/relay 实现同样的持久化投递，但支持跨机器 |
| P2P 消息（任意 teammate 间直接通信） | 无 leader 瓶颈的 Message 路由 | Agent Teams 允许 teammate 间直接通信，不经过 lead 中转——zchat 同样采用 P2P 路由，避免单点瓶颈 |
| Delegate mode（lead 只协调不执行） | Annotation(priority) 机制 | Delegate mode 将 lead 定位为纯调度者。zchat 通过 Annotation priority 实现类似效果：@mention 的 Agent 获得 CRITICAL 优先级，其他成员按 NORMAL 接收 |
| 自领取任务 + 依赖感知 | Room 内 Agent 自主响应 | Agent Teams 的 teammate 自动认领未被占用的 unblocked task，无需 lead 逐个分配。zchat 的 Agent 基于 Annotation priority 自主决定响应顺序，理念一致 |
| broadcast 消息（慎用，成本线性增长） | Room 广播规则 | Agent Teams 明确警告 broadcast 的 token 成本与成员数成正比。zchat 的房间广播也需要同样的设计意识——每个 Agent 成员都是一个完整 context window |

**注意差异**：Agent Teams 限于单机（文件系统协调），无固定 leadership 转让，不支持 Agent 迁移。zchat 需解决跨机器投递、Owner 转让（grant）、离线补偿等 Agent Teams 不涉及的问题。

### 2.2 来自 Claude-to-IM

**来源**：[github.com/op7418/Claude-to-IM](https://github.com/op7418/Claude-to-IM)，MIT。从 [CodePilot](https://github.com/op7418/CodePilot) 提取。

**与 zchat 的关系**：Claude-to-IM 将 Claude Code 的消息桥接到 IM 平台（Telegram/Discord/飞书/QQ）。它的 Channel Router 解决了"如何将消息从 Agent 路由到正确的聊天频道"，Delivery Layer 解决了"如何可靠投递到可能离线的对端"——这两个问题与 zchat-com 的 Message 路由和 outbox/relay 机制高度同构。zchat 面对的是 Zenoh topic 而非 IM API，但路由和投递的设计模式可以复用。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| Channel Router（地址 → session 绑定） | Message 路由基于 Index | Claude-to-IM 将 IM chatId 绑定到 CC session，按绑定关系路由消息。zchat 将 Room/DM 绑定到 Index topic，思路一致但路由目标从"IM 频道"变为"Zenoh key expression" |
| 权限请求转发（流内阻塞 → IM 按钮 → 回调解除） | Message(content_type=acp.request_permission) → callback | Claude-to-IM 在消费 SSE 流时同步转发权限请求到 IM，用户点击按钮后回调解除阻塞。zchat 通过 Zenoh 将权限请求 Message 路由给 Operator，机制不同但流程同构 |
| 可靠投递（分块 + 去重 + 分类重试 + 指数退避） | outbox/relay 机制 | Claude-to-IM 将投递失败分为 rate_limit/server_error/network（可重试）和 client_error/parse_error（不重试），配合指数退避和 jitter。zchat 的 outbox/relay 需要类似的错误分类和重试策略 |
| 双层 offset 安全（fetchOffset / committedOffset） | store 的 ACK 机制 | Telegram adapter 分离"已拉取"和"已确认"两个 offset，保证 crash 后不丢消息。zchat 的 DeliveryConfirm 机制解决相同问题 |
| Adapter 注册表（插件式多平台） | 未来扩展模式参考 | Claude-to-IM 通过 side-effect import 自注册 adapter，添加新平台只需一个文件。zchat 当前仅支持 CC backend，但未来扩展其他 Agent 时可参考此模式 |

**注意差异**：Claude-to-IM 面对的是 IM HTTP API（有平台限制如消息长度、速率限制），zchat 面对的是 Zenoh P2P（无外部速率限制但需处理 peer 离线）。投递层的约束不同，但可靠投递的设计模式是通用的。

---

## 3. Identity：网络中的参与者

### 3.1 人类身份

`alice@onesyn`。`user` 来自 `gh auth login`，`network` 为 LAN 网络名。

### 3.2 Agent 身份

`alice:ppt-maker@onesyn`。`agent` 由用户 spawn 时命名。携带 `owner`/`operator`/`observers`。

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

join / leave / offline / online / migrating / migrated / reclaimed / closed → Message(content_type=system_event) 广播。

---

## 5. Message：路由与投递

### 5.1 统一模型

所有通信——团队消息、ACP、系统事件、迁移 bundle——都是 Message。content_type 决定 payload 解释。

### 5.2 路由规则

Message 产生后，Hook(OnRoute) 执行：
1. 根据 target 选择主 Index（dm/room/broadcast）
2. 如果 target 是 Agent，追加 ACP Index
3. 如果 sender/target 在某 Room 中，追加 Room Index
4. 为每个接收者附加 Annotation

例：bob @alice:ppt-maker 在 #alice-workshop：
- 主 Index: `zchat/acp/alice-ppt-maker/request`
- 扩散: `zchat/room/alice-workshop`
- Annotation: ppt-maker=CRITICAL, alice=HIGH, charlie=NORMAL

### 5.3 Annotation 附加

| key | 判定 |
|---|---|
| priority | @mention→CRITICAL; @all→HIGH; 房间成员→NORMAL; 广播→LOW |
| injection_path | 查 Agent access mode → zchat/hybrid/human |
| room_context | 来源房间 |

### 5.4 房间广播规则

房间内所有 Agent 成员各自按优先级接收。@人类 时，同房间 Agent 按 NORMAL 也收到。

---

## 6. Timeline：有序视图与同步

### 6.1 scope 与 entries

每个 Room / DM 有一个 Timeline。entries 按 ts 排序。

### 6.2 gap 检测与填充

离线期间产生 gap。重连后 queryable 从 peer 拉取 → `timeline.fill_gaps()` → dedup + 排序。

### 6.3 outbox / relay / inbox

```
~/.zchat/store/
├── outbox/    ← 本机产生的、目标离线的数据
├── relay/     ← 帮其他人暂存的副本
└── inbox/     ← 重连后拉取到的数据
```

由 Index 的 `retention="relay"` 驱动。写入流程：目标离线 → outbox → 广播 RelayRequest → 在线 peer 存 relay/ 副本。读取：重连 → queryable → peer 从 outbox/relay 返回 → merge + dedup → inbox。

### 6.4 清理

DeliveryConfirm → 删除 outbox + relay。超时 30 天清理。

### 6.5 配置

```toml
[sync]
replication = 2
cleanup_days = 30
```

---

## 7. stdio Bridge

`stdio_bridge.py`：ACP Message（`"jsonrpc": "2.0"`）和团队 Message 共存于同一 stdin/stdout 管道，通过 content_type 区分路由。

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

| 模块 | 职责 |
|---|---|
| core.py | ZChatCore facade |
| message_router.py | 路由 + Index + Hook(OnRoute) + Annotation |
| network.py | 网络创建/发现/加入 |
| room.py | Room CRUD + 成员 + SystemEvent |
| presence.py | 心跳 + peer 列表 + 状态 |
| identity.py | gh auth + Identity |
| config.py | 3 层配置 + sync |
| store/outbox.py | 待发 |
| store/relay.py | 帮存 |
| store/inbox.py | 收到 |
| sync.py | Timeline gap + queryable + merge + dedup + ACK |
| stdio_bridge.py | Zenoh ↔ stdio |

---

## 10. 边界

| 范围内 | 范围外 |
|---|---|
| Identity + 认证 + 网络 | Agent 执行 (acp) |
| Room CRUD | Hook 调度 (acp) |
| Message 路由 + Annotation | TUI 渲染 (tui) |
| Timeline + store + sync | 迁移逻辑 (acp) |
| stdio bridge | CLI 子命令 (cli) |

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-protocol](./02-protocol.md) · [zchat-acp](./04-acp.md) · [zchat-cli](./05-cli.md) · [zchat-tui](./06-tui.md)
- [开发阶段](./08-dev-phases.md) · [E2E](./07-e2e-scenarios.md) · [MVP](./09-mvp-implementation.md) · [测试](./10-mvp-testcases.md)
