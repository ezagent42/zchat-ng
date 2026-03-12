# ZChat 架构概览 v0.0.5.1
## 原语体系与模块关系

---

## 1. ZChat 是什么

ZChat 是一个 LAN 多人 AI Agent 协作工具，让 2-5 人的开发团队实现人 ↔ 人、人 ↔ Agent、Agent ↔ Agent 的实时通信。所有通信基于 Eclipse Zenoh P2P 网络。当前支持 Claude Code 作为 Agent backend。

---

## 2. 原语体系：4×2

### 2.1 构建层

| 原语 | 一句话 |
|---|---|
| **DataType** | 所有结构化数据的基础类型声明 |
| **Hook** | 附着在事件上的可执行操作（runtime=zchat 或 agent） |
| **Annotation** | 附着在数据上的动态元信息（per-recipient） |
| **Index** | 数据的可寻址性 + 路由 + 持久化声明 |

### 2.2 通信层

| 原语 | 一句话 |
|---|---|
| **Identity** | 网络中每个参与者的唯一标识 |
| **Room** | 一组 Identity 的通信空间 |
| **Message** | 通信的基本单元（ACP 也是 Message） |
| **Timeline** | Message 在某 scope 内的有序视图 + 时间空洞 |

### 2.3 两层关系

```
构建层为通信层提供材料和工具：
  DataType   → Message.content 的类型
  Hook       → Message 流经系统时触发的操作
  Annotation → Message 上的 per-recipient 元信息
  Index      → Message 的寻址 + 路由 + 持久化

通信层描述通信结构：
  Identity   → 谁在说话
  Room       → 在哪说话
  Message    → 说了什么
  Timeline   → 按什么顺序看到
```

详细定义见 [zchat-protocol](./02-protocol.md)。

---

## 3. 包架构

```
              zchat-protocol
            （原语定义层）
             /              \
        zchat-com          zchat-acp
      （人类侧通信）       （Agent 侧控制）
             \              /
          zchat-cli
        （统一命令接口）
               |
          zchat-tui
         （TUI 前端）
```

### 依赖关系

```
zchat-protocol:  无依赖
zchat-com:       → zchat-protocol
zchat-acp:       → zchat-protocol
zchat-cli:       → zchat-com + zchat-acp    ← 唯一同时依赖两者
zchat-tui:       → zchat-cli                ← 不直接依赖 com/acp
```

### 包职责

| 包 | 核心原语 | 职责 |
|---|---|---|
| [zchat-protocol](./02-protocol.md) | 全部 8 个 schema | 类型定义 + 常量 |
| [zchat-com](./03-com.md) | Identity, Room, Message, Timeline | 路由, Annotation, sync, store |
| [zchat-acp](./04-acp.md) | Hook, Access | 调度, tmux backend, spawn, migrate |
| [zchat-cli](./05-cli.md) | — | com + acp 组合调用, Shell 命令 |
| [zchat-tui](./06-tui.md) | — | Timeline 渲染, 对话框, 引导流程 |

### 原语 → 包映射

| 原语 | 定义在 | 实现在 |
|---|---|---|
| DataType | protocol | 所有包使用 |
| Hook | protocol (schema) | acp (调度) |
| Annotation | protocol (schema) | com (路由时附加) |
| Index | protocol (声明) | com (路由) + acp (订阅) |
| Identity | protocol (格式) | com (认证 + 管理) |
| Room | — | com (CRUD) |
| Message | protocol (基类) | com (路由), cli (构造 + 发送) |
| Timeline | protocol (schema) | com (sync), tui (渲染) |

---

## 4. ACP 统一为 Message

所有通信——团队消息、ACP 调用、系统事件、迁移 bundle——都是 Message。`content_type` 决定 payload 解释方式。Hook(OnRoute) 决定 Message 到达哪些 Index。

CC→Room 和 Room→CC 不是"转化"，是同一条 Message 路由到多个 Index。

---

## 5. 数据同步：outbox / relay / inbox

每个 zchat-com 实例维护三个本地存储，解决 P2P "sender 和 receiver 不同时在线"问题。由 Index 的 `retention="relay"` 驱动。详见 [zchat-com](./03-com.md#6-timeline有序视图与同步)。

---

## 6. CLI 替代 MCP

runtime="agent" 的 Hook 通过 zchat CLI 子命令实现，不通过 MCP。Agent hook 脚本调用 `zchat bundle-return` 等命令。这保证了 Agent-agnostic——不依赖 CC 的 MCP 机制。详见 [zchat-cli](./05-cli.md)。

---

## 7. Spawn 配置分层：Template + Agent

Spawn 配置分为两层，存放在不同目录：

```
.zchat/
├── templates/     ← 角色模板（"工程师"）—— 可复用蓝图，团队共享
│   └── coder.toml
└── agents/        ← Agent 实例（"张三"）—— 某个具体任务的 agent
    └── ppt-maker.toml  (inherits = "coder")
```

Agent 实例通过 `inherits` 字段指向 template。解析顺序：agent TOML → template TOML → 内置默认值。

---

## 相关文档

- 设计: [protocol](./02-protocol.md) · [com](./03-com.md) · [acp](./04-acp.md) · [cli](./05-cli.md) · [tui](./06-tui.md)
- 场景: [E2E](./07-e2e-scenarios.md) · [测试](./10-mvp-testcases.md)
- 实现: [MVP](./09-mvp-implementation.md) · [开发阶段](./08-dev-phases.md)
