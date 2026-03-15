# ZChat 架构概览 v0.0.6.3.1
## 依赖反转 + 原语体系 + 模块关系

---

## 1. ZChat 是什么

ZChat 是一个 LAN 多人 AI Agent 协作工具，让 2-5 人的开发团队实现人 ↔ 人、人 ↔ Agent、Agent ↔ Agent 的实时通信。所有通信基于 Eclipse Zenoh P2P 网络。当前支持 Claude Code 作为 Agent backend。

### 1.1 核心架构思想：依赖反转 *(v0.0.6.3.1)*

传统分层：底层定义类型 → 中层实现逻辑 → 上层组合调用。zchat 反转这个依赖方向：

**zchat-cli 是核心层**——它定义所有操作的语义（send、spawn、watch、ask...）和 Backend 接口契约（ComBackend、AcpBackend Protocol）。

**zchat-protocol 是 cli 需求的形式化**——cli 的操作涉及 Message、Room、Identity、View 等概念，protocol 将它们声明为类型。protocol 不是「底层基石」，而是「cli 语义的数据化表达」。

**zchat-com 和 zchat-acp 是可替换的 Backend**——com 实现 ComBackend（如何传输），acp 实现 AcpBackend（如何适配 Agent）。它们通过接口注入 cli，cli 不 import 它们的具体模块。

```
    zchat-cli（核心层：操作定义 + Backend 接口）
        │
        │ 依赖类型定义
        ▼
    zchat-protocol（数据层：CLI 需求的形式化）
        ▲               ▲
        │ implements     │ implements
        │ ComBackend     │ AcpBackend
    zchat-com          zchat-acp
   （传输实现）       （适配实现）
```

**为什么这样设计**：

- 如果明天用 NATS 替换 Zenoh，只需要一个新的 ComBackend 实现，cli 不改一行
- 如果支持 Gemini CLI 作为 Agent backend，只需要一个新的 AcpBackend adapter，cli 不改一行
- Extension 的本质更清晰——Extension = 新的 cli 操作 + 对应的 Backend 实现
- Phase 0 锁定的是 cli 定义的接口（ComBackend/AcpBackend Protocol），不是 com/acp 内部实现

### 1.2 对称性：万物皆 Participant

协议层不区分 Editor/Agent 固定角色。所有参与方（人类、CC、Gemini CLI、自定义 agent）都是 **Participant**。谁发消息谁就是当前 turn 的发起方，角色随对话动态切换。

### 1.3 Agent 交互模式

**AFK Mode 为默认模式**。Agent 以 headless 子进程运行（CC 使用 `--input-format stream-json`），无 TUI。

**Direct Mode（tmux 集成）推迟实现**。人类需要直接交互时使用 attach/detach 机制：

```
zchat session attach <agent>   → 暂停 headless，获取 session ID
claude --resume <session-id>   → 人类直接在 CC TUI 中交互
zchat session detach <agent>   → 恢复 headless + 回扫未读消息
```

### 1.4 CC ↔ ZChat 交互模型

**模型 2（被动/默认）**：Room event → adapter 构造 enriched message → JSONL stdin → CC。CC stdout → adapter → 自动路由回源 Room。

**模型 1（主动/可选）**：CC 通过 AgentSkill 学会 zchat CLI。CC 可 `tool_use: Bash("zchat send ...")` 跨 Room 操作。Zenoh 本身就是 IPC——CLI 进程以 Zenoh peer 身份连入同一网络，不需要额外机制。

### 1.5 前端策略

**CLI + AgentSkill 优先**。人类通过 `zchat send` / `zchat watch` / `zchat ask` 等 CLI 命令操作。Agent 通过 `zchat.md` AgentSkill 学会调用同一套 CLI。TUI 推迟实现。

---

## 2. 原语体系：4×2

### 2.1 构建层（底层实现工具）

| 原语 | 一句话 |
|---|---|
| **ContentType** | 所有结构化数据的基础类型声明（event content 结构等） |
| **Hook** | 附着在事件上的可执行操作（runtime=zchat 或 agent） |
| **Annotation** | 附着在数据上的动态元信息（per-recipient 差异化） |
| **Index** | 数据的可寻址性 + Zenoh key-expression 路由 + 持久化声明 |

### 2.2 通信层（对齐 Matrix 协议）

| 原语 | 一句话 | Matrix 对应 |
|---|---|---|
| **Identity** | 网络中每个参与者的唯一标识（account:label） | Matrix User ID |
| **Room** | 一组 Identity 的通信空间 | Matrix Room |
| **Message** | 通信的基本单元，序列化为 ZChatEvent | Matrix Event |
| **View** | Message 在某 scope 内的投影规则 | Matrix Room Timeline (扩展) |

### 2.3 两层关系

```
构建层是实现工具，通信层对齐 Matrix：

  ContentType → 定义 Message.content 的类型结构
  Hook       → Message 流经系统时触发的操作
  Annotation → 同一 Message 对不同接收者的差异化元信息
  Index      → Message 的 Zenoh 寻址 + 路由规则

通信层直接对齐 Matrix 概念：
  Identity   → 谁在说话
  Room       → 在哪说话
  Message    → 说了什么（封装为 ZChatEvent）
  View       → 如何看到（支持 filter/sort/group/fold）
```

这些原语从 cli 的操作需求推导：`zchat send` 需要 Message + Room + Identity；`zchat watch` 需要 View；`zchat spawn` 需要 SpawnConfig (ContentType) + Hook + Index。详见 [zchat-protocol](./03-protocol.md)。

---

## 3. 三分法：Core / Extension / 推迟模块

### 3.1 划分标准

- **Core**：MVP 必须实现
- **Extension**：去掉后 zchat 仍然是 zchat。Extension = 新的 cli 操作 + 对应的 Backend 实现
- **推迟模块**：zchat 概念的一部分，但 MVP 先不做

### 3.2 Extension（独立包）

- `ext-migrate` — 新增 cli 操作 grant/reclaim + 对应实现
- `ext-offline` — 增强 ComBackend 的投递可靠性
- 未来：`ext-socialware`、`ext-channel-bridge` 等

### 3.3 推迟模块

- `zchat-tui` — CLI 之上的标准 TUI 前端
- Direct Mode — tmux 集成

详见 [Extension 机制](./06-extension.md)。

---

## 4. 包架构

### 4.1 依赖方向

```
zchat-cli:       → zchat-protocol        ← 核心层，定义操作 + Backend 接口
zchat-protocol:  无依赖                    ← 数据层，类型定义
zchat-com:       → zchat-protocol        ← 传输实现，implements ComBackend
zchat-acp:       → zchat-protocol        ← 适配实现，implements AcpBackend
zchat-ext-*:     → zchat-protocol        ← Extension，通过 Hook/Annotation 挂载
zchat-tui:       → zchat-cli             ← 推迟实现
```

**关键：cli 不依赖 com/acp。com/acp 实现 cli 定义的接口，在启动时注入。**

### 4.2 启动时组装

```python
# zchat/__main__.py
from zchat_cli import ZChatCLI
from zchat_com import ZenohComBackend
from zchat_acp import HeadlessAcpBackend

com = ZenohComBackend()
acp = HeadlessAcpBackend()
cli = ZChatCLI(com=com, acp=acp)
await cli.start()
```

### 4.3 包职责

| 包 | 核心职责 |
|---|---|
| [zchat-cli](./02-cli.md) | 操作语义定义 + ComBackend/AcpBackend 接口 + Shell 命令 |
| [zchat-protocol](./03-protocol.md) | 8 个原语 schema + ZChatEvent + ExtensionManifest |
| [zchat-com](./04-com.md) | implements ComBackend：Zenoh P2P + Event Store + 宽容路由 |
| [zchat-acp](./05-acp.md) | implements AcpBackend：CC Headless Adapter + enriched message + 进程池 |
| [zchat-tui](./07-tui.md) | TUI 前端 **（推迟实现）** |

### 4.4 原语 → 包映射

| 原语 | 定义在 | 实现在 |
|---|---|---|
| ContentType | protocol | 所有包使用 |
| Hook | protocol (schema) | acp (调度), extension (注册) |
| Annotation | protocol (schema) | com (路由时附加 per-recipient) |
| Index | protocol (声明) | com (Zenoh 路由) |
| Identity | protocol (格式) | com (认证 + 管理) |
| Room | — | com (CRUD，对齐 Matrix Room) |
| Message | protocol (基类 + ZChatEvent) | com (路由), acp (构造 ZChat Operation) |
| View | protocol (schema) | com (查询), cli (watch 渲染) |

---

## 5. ACP 统一为 Event

所有通信——团队消息、ACP 操作、系统事件——都是 ZChatEvent。`type` 字段决定 payload 解释方式。

ACP 不是通信协议，而是**操作标准化层**——它定义 WHAT（不同参与方的操作的统一格式），zchat-com 定义 HOW（事件如何传输）。

协议层不区分 Editor/Agent——只有 Participant 和 Operation。Turn 方向从 `replyTo` 链中涌现。

**宽容路由**：zchat-com 对未知 content_type 的 ZChatEvent 做透传（存储 + 路由），不拒绝。

---

## 6. 数据同步

MVP 使用简单 queryable backfill：重连后通过 Zenoh queryable 从 peer 拉取最近历史事件。完整的 outbox / relay / inbox 在 ext-offline Extension 中实现。

---

## 7. Spawn 配置分层：Template + Agent

```
.zchat/
├── templates/     ← 角色模板（"工程师"）—— 可复用蓝图，团队共享
│   └── coder.toml
└── agents/        ← Agent 实例（"张三"）—— 某个具体任务的 agent
    └── ppt-maker.toml  (inherits = "coder")
```

解析顺序：agent TOML → template TOML → 内置默认值。

---

## 相关文档

- 核心: [cli](./02-cli.md) · [protocol](./03-protocol.md) · [com](./04-com.md) · [acp](./05-acp.md)
- 扩展: [extension](./06-extension.md) · [zchat.md](./zchat.md) · [tui](./07-tui.md) *(推迟)*
- 场景: [E2E](./08-e2e-scenarios.md) · [测试](./11-mvp-testcases.md)
- 实现: [MVP](./10-mvp-implementation.md) · [开发阶段](./09-dev-phases.md)
