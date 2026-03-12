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

**与 zchat 的关系**：Claude Squad 的 TUI 是目前最成熟的"多 Agent session 管理界面"——左侧 session 列表（30%）+ 右侧 tabbed 预览（70%）+ 底部菜单栏。zchat-tui 的 Dashboard Tab 直接对标其主界面，但 zchat 还需要 Chat Tab（聊天）和 Session Tab（Agent 交互），Claude Squad 不涉及这两个场景。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| 左右分栏（session list 30% + preview 70%） | Dashboard Tab 布局 | 经过 6k+ 用户验证的布局比例，session 列表需要展示状态图标、分支名、diff 统计，30% 宽度刚好 |
| Tabbed preview（Preview / Diff / Terminal 三标签） | Dashboard 内的多视角切换 | 同一个 session 需要多种视角（实时输出、代码变更、终端交互），tab 切换比切换页面更流畅 |
| Session 状态图标（spinner/绿点/暂停） | Agent 5 种状态指示 | 单字符图标在列表中信息密度高。zchat 扩展为 ●○◐ 五色方案 |
| tmux pane 尺寸同步 | Session Tab 输出渲染 | Claude Squad 将 preview pane 尺寸同步到 tmux session，保证输出换行正确。zchat 的 Session Tab 也需要同样的尺寸协调 |
| 单字符快捷键 + 菜单高亮反馈 | 键盘驱动交互 | n/N/D/Enter/Ctrl-Q 等单键操作提高效率，按键后菜单项高亮 500ms 提供视觉反馈 |
| daemon/TUI 互斥 | zchat 进程持久，TUI attach/detach | TUI 退出时 fork daemon 保持 Agent 运行，TUI 启动时 kill daemon 接管——zchat 的 attach/detach 可参考此模式 |

**注意差异**：Claude Squad 基于 bubbletea（Go），zchat 基于 Textual（Python）。两者都是 Elm 架构（事件 → 状态 → 渲染），但 widget 层 API 不同。Claude Squad 不支持多人协作 UI，zchat 需要额外的 Sidebar 展示 Peers 和 Rooms。

### 2.2 来自 termchat

**来源**：[github.com/lemunozm/termchat](https://github.com/lemunozm/termchat) — 570+ stars。

**与 zchat 的关系**：termchat 是零配置的 LAN P2P 终端聊天工具——用 UDP multicast 发现 peer，用 TCP 传输消息。它验证了"终端内的局域网聊天"这个场景的可行性。zchat-tui 的 Chat Tab 承载相同的聊天体验，但 zchat 用 Zenoh 替代 message-io，用 Textual 替代 tui-rs，且需支持 Agent 消息和 Annotation。

| 借鉴 | 应用 | 为什么借鉴 |
|---|---|---|
| 消息面板 + 输入面板的双区布局 | Chat Tab 基础结构 | termchat 实际是上下两区（消息占满剩余空间 + 输入固定 6 行），简洁有效。zchat 的 Chat Tab 在此基础上增加左侧 Sidebar（成员列表） |
| UDP multicast 自动发现 + TCP 传输 | Zenoh scout 发现 + pub/sub 传输 | termchat 用 multicast 一包发现所有 peer，然后建立 TCP 直连。zchat 用 Zenoh scout 做同样的事——验证了"零配置 LAN 发现"体验的用户接受度 |
| 系统消息三级样式（Info/Warning/Error） | SystemEvent 渲染 | join/leave/offline 等系统事件按级别着色（Cyan/Yellow/Red），在聊天流中自然区分人类消息和系统通知 |
| `?` 命令前缀 + 注册表模式 | `:` 命令系统 | termchat 用 `?` 前缀 + Command trait 注册表实现可扩展命令。zchat 改用 `:` 前缀（更接近 Vim 习惯），但注册表模式可复用 |
| 零配置启动 | `zchat` 一条命令 | termchat 的 `termchat` 一键启动体验是核心卖点。zchat 的 `uvx zchat` 追求同样的开箱即用——首次引导流程应最小化 |

**注意差异**：termchat 无用户列表面板（peer 只出现在 join/leave 消息中），无消息持久化，无离线补偿。zchat 需要 Sidebar 展示在线 peer/Agent/Room，以及 Timeline 的 gap 填充机制——这些是 termchat 不涉及的。

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
