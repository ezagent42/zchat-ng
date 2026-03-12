# zchat-tui 设计文档 v0.0.5.1
## TUI 前端

---

## 1. 概览

zchat-tui 是 **zchat-cli 的交互式前端**。只依赖 zchat-cli，不直接依赖 com 或 acp。

```
        zchat-cli
            |
     → zchat-tui ←
```

定位：薄渲染壳。所有业务逻辑在 com/acp 中，所有命令组合在 cli 中。

---

## 2. Where to Steal

### 2.1 来自 Claude Squad

**来源**：[github.com/smtg-ai/claude-squad](https://github.com/smtg-ai/claude-squad) — 6k+ stars。

| 借鉴 | 应用 |
|---|---|
| Session list + preview | Dashboard Tab |
| Daemon 后台 | zchat 进程持久，TUI attach/detach |
| 快捷键 | n 新建、Enter 聚焦、Ctrl-q 退出 |

### 2.2 来自 termchat

**来源**：[github.com/lemunozm/termchat](https://github.com/lemunozm/termchat) — 570+ stars。

| 借鉴 | 应用 |
|---|---|
| IRC 3-panel | Chat Tab |
| `:` 命令 | Vim 风格 |
| 系统消息样式 | `***` + 颜色 |
| 零配置 | `zchat` 一条命令 |

---

## 3. 引导流程

首次：检测 identity → 不存在 → gh auth login → 检测网络 → 无 peer → 命名 → 主界面。
后续：加载 identity → 发现网络 → 主界面。

---

## 4. 布局

```
┌──────────────────────────────────────────────────┐
│ [Dashboard] [Chat] [Session]       alice@onesyn  │
├──────────┬───────────────────────────────────────┤
│ Sidebar  │  当前 Tab                              │
│ ▸ Peers  │                                       │
│ ▸ Sessions (● ○ ◐)                               │
│ ▸ Rooms  │                                       │
├──────────┴───────────────────────────────────────┤
│ :                                      [Ctrl+?]  │
└──────────────────────────────────────────────────┘
```

| Tab | 渲染原语 |
|---|---|
| Dashboard | Session (Identity + 5 种状态) |
| Chat | Timeline (Message + Annotation) |
| Session | Agent 输出 (Message acp.session.update) |

Session Tab：只读 → Ctrl+E 交互（仅 Operator）→ Escape 返回。5 分钟超时。

Agent 状态：● running (绿) / ○ migrated (灰) / ○ offline (红) / ○ reclaimed (黄) / ◐ bundle_pending (蓝)

---

## 5. 命令 → CLI 映射

| TUI 命令 | ZChatCLI 方法 |
|---|---|
| `:template init <n>` | `cli.template_init(n)` |
| `:template list` | `cli.template_list()` |
| `:agent init <n> --from <t>` | `cli.agent_init(n, t)` |
| `:agent list` | `cli.agent_list()` |
| `:spawn <agent>` | `cli.spawn(agent)` → preview → 确认 → `cli.spawn_confirm()` |
| `:spawn --template <t> --name <n>` | `cli.spawn_adhoc(t, n)` → preview → 确认 |
| `:room create <n>` | `cli.room_create(n)` |
| `:room invite <r> <u>` | `cli.room_invite(r, u)` |
| `:session attach <id>` | `cli.attach(id)` → Session Tab |
| `:session grant <id> <u>` | 确认对话框 → `cli.grant(id, u)` |
| `:session reclaim <id>` | 确认对话框 → `cli.reclaim(id)` |
| `:session kill <id>` | 确认对话框 → `cli.kill(id)` |
| `:afk` / `:back` | `cli.afk()` / `cli.back()` |
| Chat 发消息 | `cli.send(target, content)` |

---

## 6. 对话框

**Spawn 确认**：配置摘要 → Y/n/e。
**迁移确认**：列出 operator 变更。
**关闭安全**：列出受影响房间。
**Bundle 接收**：内容摘要 → 恢复/丢弃。
**Reclaim 确认**：提示 CC 脱网。

---

## 7. Timeline 渲染

离线标注：
```
─── 离线期间 (14:30 - 16:45) ───
[15:10] bob: @ppt-maker 进展如何？
─── 恢复在线 ───
```

Bundle 等待：`有 pending bundle，等待 peer 上线...`

---

## 8. 与 zchat-cli 的交互

```python
from zchat_cli import ZChatCLI
cli = ZChatCLI()
await cli.start(config_path="~/project")
cli.on_message(lambda msg: tui.display_message(msg))
cli.on_bundle_received(lambda b: tui.show_bundle_dialog(b))
cli.on_offline_sync(lambda msgs: tui.show_offline_messages(msgs))
```

---

## 9. 边界

| 范围内 | 范围外 |
|---|---|
| Timeline 渲染 | Message 路由 (com via cli) |
| 命令 → CLI 调用 | Hook 调度 (acp via cli) |
| 对话框 | Access control (acp via cli) |
| 引导流程 | CLI 实现 (cli) |

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-cli](./05-cli.md) · [zchat-protocol](./02-protocol.md) · [zchat-com](./03-com.md) · [zchat-acp](./04-acp.md)
- [开发阶段](./08-dev-phases.md) · [E2E](./07-e2e-scenarios.md) · [MVP](./09-mvp-implementation.md) · [测试](./10-mvp-testcases.md)
