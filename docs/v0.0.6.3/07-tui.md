# zchat-tui 设计文档 v0.0.6.3
## TUI 前端

> **⚠️ 推迟实现**：zchat-tui 是 zchat 的核心模块之一，但在 v0.0.6.3 MVP 中推迟实现。MVP 阶段使用 `zchat watch` + `zchat send` + AgentSkill 替代 TUI 的核心功能。以下设计完整保留，供未来实现参考。


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

## 5. Widget 组件与状态管理

### 5.1 架构概述

Textual 采用 Elm 架构：事件 → 状态变更 → 自动重渲染。zchat-tui 的状态分为两层：

- **reactive 属性**：定义在 Widget 上，变更时自动触发 `watch_*` 或 `recompose`
- **CLI 回调**：ZChatCLI 的异步回调将外部事件（新消息、状态变化、bundle 到达）转化为 Widget 的 reactive 赋值

```
ZChatCLI callbacks ──→ App.on_* handlers ──→ widget.reactive = new_value
                                                     │
                                              watch_* / recompose
                                                     │
                                               自动重渲染
```

### 5.2 ZChatApp（app.py）

主 App，唯一持有 `ZChatCLI` 实例的组件。

```
compose:
  Header（Tab 栏 + Identity 显示）
  Horizontal:
    Sidebar (20%)
    ContentSwitcher:    ← 按 active_tab 切换
      DashboardTab
      ChatTab
      SessionTab
  CommandBar
```

| reactive | 类型 | 触发 |
|---|---|---|
| `active_tab` | `str` | Tab 切换 → ContentSwitcher.current |
| `identity` | `Identity \| None` | 引导流程完成 / CLI 连接成功 |
| `connected` | `bool` | Zenoh 网络连接状态 |

**职责**：
- 注册全局 keybindings（Tab/Ctrl+Q/n/?）
- 在 `on_mount` 中调用 `cli.start()` 并注册所有 CLI 回调
- 充当 CLI 回调到 Widget 的中转：收到回调后 `post_message` 给目标 Widget
- 管理 ModalScreen（对话框通过 `push_screen` 弹出）

### 5.3 Sidebar（sidebar.py）

左侧可折叠面板，展示网络中的三类实体。

| reactive | 类型 | 数据来源 |
|---|---|---|
| `peers` | `list[Identity]` | `cli.on_presence_changed` |
| `sessions` | `list[SessionInfo]` | `cli.on_session_changed` |
| `rooms` | `list[RoomInfo]` | `cli.on_room_changed` |
| `selected` | `str \| None` | 用户点击/键盘选中 |

**SessionInfo** 包含：session_id, agent Identity, 状态（5 种）, owner, operator。

**渲染逻辑**：
- 三个 Collapsible 区域（Peers / Sessions / Rooms），各区域内用 ListItem
- Session 列表每项：状态图标 + agent 名 + operator 名
- Room 列表每项：房间名 + 成员数 + 未读计数
- 选中 Session → 切换到 Dashboard Tab 并聚焦该 session
- 选中 Room → 切换到 Chat Tab 并切换到该 room

### 5.4 DashboardTab（dashboard.py）

Session 管理视图。左右分栏，参考 Claude Squad 的 30/70 布局。

```
compose:
  Horizontal:
    SessionList (fr=3)    ← session 列表
    SessionPreview (fr=7) ← 选中 session 的预览
```

| reactive | 类型 | 说明 |
|---|---|---|
| `selected_session` | `str \| None` | 当前选中的 session_id |
| `preview_mode` | `str` | "output" / "config" / "log"（预览标签页） |

**SessionList**（子 Widget）：

| reactive | 类型 | 数据来源 |
|---|---|---|
| `sessions` | `list[SessionInfo]` | 从 Sidebar.sessions 同步 |

每项渲染：`● ppt-maker (alice) [running]`。j/k 导航，Enter 聚焦到 Session Tab。

**SessionPreview**（子 Widget）：

| reactive | 类型 | 数据来源 |
|---|---|---|
| `output_lines` | `list[str]` | `cli.on_session_output`（Agent 流式输出） |
| `config` | `SpawnConfig \| None` | 选中 session 的配置 |

输出预览通过 `RichLog` Widget 追加渲染，避免全量重绘。

### 5.5 ChatTab（chat.py）

聊天视图。上下分区，上方 Timeline 可滚动，下方输入固定高度。

```
compose:
  Vertical:
    TimelineView (fr=1)   ← 消息列表，占满剩余空间
    ChatInput (height=5)  ← 输入区域，固定 5 行
```

| reactive | 类型 | 说明 |
|---|---|---|
| `current_target` | `Target \| None` | 当前聊天目标（Room 或 DM） |
| `timeline` | `Timeline` | 当前 scope 的 Timeline 数据 |

**TimelineView**（子 Widget）：

| reactive | 类型 | 数据来源 |
|---|---|---|
| `entries` | `list[Message]` | `cli.on_message` 追加新消息 |
| `gaps` | `list[TimeGap]` | `cli.on_offline_sync` 填充 gap |

渲染规则：
- 人类消息：`[HH:MM] alice: 内容`
- Agent 消息：`[HH:MM] 🤖 ppt-maker: 内容`（Agent 前缀图标）
- SystemEvent：按级别着色（Info=Cyan, Warning=Yellow, Error=Red）
- 离线 gap：`─── 离线期间 (14:30 - 16:45) ───` 分隔线
- Annotation 高亮：CRITICAL 消息加粗，@mention 部分高亮

使用 `RichLog` 追加渲染（on_message 回调时 `write` 新行），滚动到底部。

**ChatInput**（子 Widget）：

| reactive | 类型 | 说明 |
|---|---|---|
| `draft` | `str` | 当前输入内容 |

Enter 发送 → `cli.send(target, content)`。支持 @mention 补全（Tab 触发，从 Sidebar.peers + sessions 中匹配）。以 `:` 开头时转交 CommandBar 处理。

### 5.6 SessionTab（session_tab.py）

Agent 交互视图。默认只读，Ctrl+E 进入交互模式（仅 Operator）。

| reactive | 类型 | 说明 |
|---|---|---|
| `attached_session` | `str \| None` | 当前 attach 的 session_id |
| `is_interactive` | `bool` | 是否处于交互模式 |
| `interactive_timeout` | `float` | 交互模式剩余秒数（5 分钟递减） |
| `output_lines` | `list[str]` | Agent 终端输出 |

**交互模式状态机**：

```
只读 ──Ctrl+E──→ 交互（如果是 Operator）
  ↑                    │
  └──Escape / 超时 5min─┘
```

交互模式下键盘输入通过 `cli.session_send_keys(session_id, keys)` 发送到 tmux。
只读模式下用 `RichLog` 渲染 Agent 输出流。

### 5.7 CommandBar（command_bar.py）

底部命令输入栏。

| reactive | 类型 | 说明 |
|---|---|---|
| `command_text` | `str` | 当前命令文本 |
| `suggestions` | `list[str]` | 自动补全候选 |
| `is_active` | `bool` | 命令栏是否获得焦点 |

**命令解析**：注册表模式。每个命令注册 name + parser + handler：

```
registry = {
    "spawn":   (parse_spawn,   handle_spawn),
    "room":    (parse_room,    handle_room),
    "session": (parse_session, handle_session),
    "afk":     (parse_noop,    handle_afk),
    ...
}
```

输入 `:` 时 CommandBar 获得焦点，Enter 执行，Escape 取消。部分命令（spawn/grant/reclaim/kill）执行前 `push_screen` 弹出确认对话框。

### 5.8 对话框（dialogs.py）

所有对话框继承 `ModalScreen[T]`，通过 `dismiss(result)` 返回用户选择。

| 对话框 | ModalScreen 泛型 | dismiss 值 |
|---|---|---|
| SpawnConfirmDialog | `str \| None` | "confirm" / "edit" / None（取消） |
| MigrateConfirmDialog | `bool` | True（确认）/ False（取消） |
| CloseSafetyDialog | `bool` | True（强制关闭）/ False（取消） |
| BundleReceiveDialog | `bool` | True（恢复）/ False（丢弃） |
| ReclaimConfirmDialog | `bool` | True（确认）/ False（取消） |

调用模式（在 App 或 CommandBar 中）：

```python
def handle_spawn(self, agent: str):
    config = await cli.spawn(agent)  # 获取预览配置

    def on_confirm(result: str | None):
        if result == "confirm":
            cli.spawn_confirm()
        elif result == "edit":
            # 打开 TOML 编辑
            ...

    self.app.push_screen(SpawnConfirmDialog(config), on_confirm)
```

### 5.9 CLI → Widget 数据流总览

| CLI 回调 | 目标 Widget | 更新的 reactive |
|---|---|---|
| `on_message(msg)` | ChatTab.TimelineView | `entries` 追加 |
| `on_session_changed(info)` | Sidebar, DashboardTab.SessionList | `sessions` |
| `on_session_output(id, lines)` | DashboardTab.SessionPreview, SessionTab | `output_lines` |
| `on_presence_changed(peers)` | Sidebar | `peers` |
| `on_room_changed(rooms)` | Sidebar | `rooms` |
| `on_bundle_received(bundle)` | App → push BundleReceiveDialog | — |
| `on_offline_sync(msgs)` | ChatTab.TimelineView | `gaps` 填充 + `entries` 补充 |
| `on_permission_request(req)` | App → push PermissionDialog（Operator 场景） | — |

### 5.10 Phase 0 Mock 策略

Phase 0 中所有 CLI 回调由 MockZChatCLI 驱动：

- `on_message`：定时 1 秒后返回假回复
- `on_session_changed`：spawn 后立即推送 running 状态
- `on_presence_changed`：启动时推送 hardcoded peers
- `on_room_changed`：启动时推送 hardcoded rooms
- 其他回调：按需触发，返回合理假数据

全部 Widget 的 reactive 属性、compose 结构、CLI 回调绑定在 Phase 0 就位。Phase 1 只替换 MockZChatCLI → 真实 ZChatCLI，Widget 层不变。

---

## 6. 命令 → CLI 映射（同 §5.7 命令注册表）

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

## 7. 对话框（同 §5.8 ModalScreen）

**Spawn 确认**：配置摘要 → Y/n/e。
**迁移确认**：列出 operator 变更。
**关闭安全**：列出受影响房间。
**Bundle 接收**：内容摘要 → 恢复/丢弃。
**Reclaim 确认**：提示 CC 脱网。

---

## 8. Timeline 渲染（同 §5.5 TimelineView）

离线标注：
```
─── 离线期间 (14:30 - 16:45) ───
[15:10] bob: @ppt-maker 进展如何？
─── 恢复在线 ───
```

Bundle 等待：`有 pending bundle，等待 peer 上线...`

---

## 9. 与 zchat-cli 的交互（同 §5.9 数据流）

```python
from zchat_cli import ZChatCLI
cli = ZChatCLI()
await cli.start(config_path="~/project")
cli.on_message(lambda msg: tui.display_message(msg))
cli.on_bundle_received(lambda b: tui.show_bundle_dialog(b))
cli.on_offline_sync(lambda msgs: tui.show_offline_messages(msgs))
```

---

## 9.1 AFK Mode TUI 组件 *(new in v0.0.6)*

### AskUserQuestion 交互式表单

当 AFK 模式下的 Agent 通过 ACP `{type: "ask"}` 向人类提问时，TUI 渲染为交互式表单：

```
┌─ alice:ppt-maker has a question ──────────────────────┐
│                                                        │
│  Q: 请选择 PPT 的主题风格：                             │
│  ○ 商务简约                                            │
│  ● 科技感                                              │
│  ○ 学术                                                │
│                                                        │
│  Q: 是否需要生成配图？                                  │
│  ○ 是    ● 否                                          │
│                                                        │
│  [Submit]  [Skip]                                      │
└────────────────────────────────────────────────────────┘
```

Submit → ZChat Operation `{type: "answer"}` → CC Headless Adapter → JSONL stdin。Skip → timeout 语义，adapter 注入默认回答。

### Agent 模式指示器

Session 列表和 Session Tab 标题栏中显示当前模式：

```
Sessions
  ● alice:ppt-maker  [AFK]     ← AFK 模式（headless）
  ● alice:reviewer   [Direct]  ← Direct 模式（tmux TUI）
  ○ bob:api-dev      [Idle]    ← AFK 已回收，sessionId 保留
```

### Thinking Panel

AFK 模式下 Agent 的 `{type: "thinking"}` stream 渲染为可折叠面板（参考 NeoClaw 的飞书流式卡片 thinking panel）：

```
┌─ alice:ppt-maker is thinking... ──────────────────────┐
│ ▸ 让我分析一下 PPT 结构需求...                          │
│   用户需要一个关于 Q3 销售数据的展示...                   │
│   我应该先创建大纲，然后逐页填充...                      │
└────────────────────────────────────────────────────────┘
```

thinking 结束后自动折叠，最终 `{type: "msg"}` 消息正常显示在 Timeline 中。

---

## 10. 边界

| 范围内 | 范围外 |
|---|---|
| Timeline 渲染 | Message 路由 (com via cli) |
| 命令 → CLI 调用 | Hook 调度 (acp via cli) |
| 对话框 | Access control (acp via cli) |
| 引导流程 | CLI 实现 (cli) |

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-cli](./02-cli.md) · [zchat-protocol](./03-protocol.md) · [zchat-com](./04-com.md) · [zchat-acp](./05-acp.md)
- [开发阶段](./09-dev-phases.md) · [E2E](./08-e2e-scenarios.md) · [MVP](./10-mvp-implementation.md) · [测试](./11-mvp-testcases.md)
