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

| 借鉴 | 应用 |
|---|---|
| Inbox mailbox | Zenoh 传输的 inbox（Index retention=relay） |
| P2P messaging | 无 leader 瓶颈 |
| Delegate mode | Annotation(priority) 机制 |

### 2.2 来自 Claude-to-IM

**来源**：[github.com/op7418/Claude-to-IM](https://github.com/op7418/Claude-to-IM)，MIT。从 [CodePilot](https://github.com/op7418/CodePilot) 提取。

| 借鉴 | 应用 |
|---|---|
| Channel Router | Message 路由基于 Index |
| Permission flow | Message(content_type=acp.request_permission) → callback |
| Delivery retry | outbox/relay 机制 |

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
