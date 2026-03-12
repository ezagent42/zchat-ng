# zchat-cli 设计文档 v0.0.5.1
## 统一命令接口层

---

## 1. 概览

zchat-cli 是 zchat-com 和 zchat-acp 之上的统一命令接口。唯一同时依赖两者的层。

提供 Python API（供 zchat-tui）和 Shell 命令（供 agent hook + 用户）。

---

## 2. Python API

```python
class ZChatCLI:
    # 生命周期
    async def start(self, config_path: str) -> None
    async def stop(self) -> None

    # 事件订阅
    def on_message(self, cb) -> None
    def on_session_update(self, cb) -> None
    def on_permission_request(self, cb) -> None
    def on_bundle_received(self, cb) -> None
    def on_offline_sync(self, cb) -> None
    def on_migration_progress(self, cb) -> None

    # Identity + Network
    async def get_identity(self) -> Identity
    async def get_network(self) -> NetworkInfo
    async def get_peers(self) -> list[Identity]

    # Room
    async def room_create(self, name: str) -> Room
    async def room_invite(self, room: str, invitee: str) -> None
    async def room_leave(self, room: str) -> None
    async def rooms(self) -> list[Room]

    # Message
    async def send(self, target: str, content: str) -> Message

    # Template 管理
    async def template_init(self, name: str) -> Path
    async def template_list(self) -> list[TemplateInfo]

    # Agent 实例管理
    async def agent_init(self, name: str, from_template: str) -> Path
    async def agent_list(self) -> list[AgentConfigInfo]

    # Spawn 执行
    async def spawn(self, agent_name: str, resume: bool = False) -> SpawnPreview
    async def spawn_adhoc(self, template: str, name: str) -> SpawnPreview
    async def spawn_confirm(self, preview: SpawnPreview) -> SessionInfo
    async def spawn_cancel(self, preview: SpawnPreview) -> None

    # Session 控制
    async def afk(self, session_id: str) -> None
    async def back(self, session_id: str) -> None
    async def status(self, session_id: str = None) -> SessionStatus | NetworkStatus
    async def sessions(self) -> list[SessionInfo]

    # Session 共享
    async def attach(self, agent_id: str) -> AsyncIterator[Message]
    async def detach(self, agent_id: str) -> None
    async def grant(self, agent_id: str, to_user: str) -> None
    async def reclaim(self, agent_id: str) -> None
    async def kill(self, agent_id: str) -> None

    # Agent Hook 回调
    async def bundle_return(self, session_id: str) -> None
    async def check_reclaim(self, session_id: str) -> bool
```

---

## 3. Shell 命令

```bash
# 无参数 → TUI
zchat

# Template 管理
zchat template init <name>                   # 从内置模板生成 .zchat/templates/<name>.toml
zchat template list                          # 列出可用 template

# Agent 实例管理
zchat agent init <name> --from <template>    # 从 template 创建 .zchat/agents/<name>.toml
zchat agent list                             # 列出 agent 实例配置

# Spawn 执行
zchat spawn <agent_name> [--resume] [--yes]  # 启动 agent 实例
zchat spawn --template <t> --name <n> [--yes]  # 临时从 template 启动（不创建持久配置）

# Network + Room
zchat network
zchat peers
zchat rooms
zchat room create <n>
zchat room invite <room> <user>
zchat room leave <room>

# Message
zchat send <target> <message>

# Session
zchat afk <session>
zchat back <session>
zchat status [session] [--json] [--check-reclaim]
zchat sessions
zchat session attach <id>
zchat session grant <id> <user>
zchat session reclaim <id>
zchat session kill <id>

# Agent Hook 回调
zchat bundle-return <session>

# 前置检查
zchat preflight
```

---

## 4. 内部逻辑

不含业务逻辑——组合调用 com + acp：

```python
async def grant(self, agent_id, to_user):
    self.acp.validate_grant_permission(agent_id, self.identity)
    bundle = await self.acp.migrate_out(agent_id)
    await self.com.transfer_bundle(bundle, to_user)
    await self.com.broadcast_system_event(rooms, "migrated")

async def spawn(self, agent_name, resume=False):
    config = self.com.load_agent_config(agent_name)  # 解析 inherits
    preview = self.acp.prepare_spawn(config)
    return preview
```

---

## 5. Agent Hook 脚本

zchat_inject 安装到 CC：

```bash
# ~/.claude/hooks/session-end.sh
#!/bin/bash
zchat bundle-return "$ZCHAT_SESSION_ID"

# ~/.claude/hooks/after-prompt.sh
#!/bin/bash
if zchat status "$ZCHAT_SESSION_ID" --check-reclaim; then
  echo "⚠ 已脱网，可继续本地使用。"
fi
```

---

## 6. 前置检查

```
$ zchat preflight
✓ Python 3.12.3
✓ tmux 3.4
✓ gh 2.45.0 (已登录: alice)
✓ claude (Claude Code v2.1.29)
```

---

## 7. 边界

| 范围内 | 范围外 |
|---|---|
| 统一 API + Shell | Message 路由(com), Hook 调度(acp), TUI(tui), 原语(protocol) |
| template/agent 配置管理 | 配置文件格式定义(protocol SpawnConfig) |
| preflight | — |

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-com](./03-com.md) · [zchat-acp](./04-acp.md) · [zchat-tui](./06-tui.md)
- [开发阶段](./08-dev-phases.md) · [E2E](./07-e2e-scenarios.md) · [MVP](./09-mvp-implementation.md) · [测试](./10-mvp-testcases.md)
