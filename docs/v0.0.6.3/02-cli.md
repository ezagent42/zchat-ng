# zchat-cli 设计文档 v0.0.6.3.1
## 核心层：操作定义 + Backend 接口

---

## 1. 概览

zchat-cli 是 ZChat 的**核心层**——它定义所有操作的语义、Backend 接口契约、以及 Shell 命令。

**v0.0.6.3.1 定位变更**：cli 不再是 com/acp 之上的「粘合层」。cli 是最底层的依赖——它定义「能做什么」，protocol 形式化「操作涉及的数据类型」，com/acp 实现「具体怎么做」。

```
    → zchat-cli ←（核心层）
        │
        ▼
    zchat-protocol（数据层）
        ▲           ▲
    zchat-com    zchat-acp（Backend 实现）
```

**cli 不 import com/acp。com/acp 实现 cli 定义的 Protocol 接口，在启动时注入。**

---

## 2. Backend 接口契约 *(new in v0.0.6.3)*

cli 定义两个 Protocol——ComBackend 和 AcpBackend。Phase 0 锁定这两个接口。

### 2.1 ComBackend Protocol

```python
class ComBackend(Protocol):
    """传输层接口——cli 不关心底层是 Zenoh 还是 NATS"""

    # Identity + Network
    async def get_identity(self) -> Identity: ...
    async def get_network(self) -> NetworkInfo: ...
    async def get_peers(self) -> list[Identity]: ...
    async def setup_identity(self, gh_username: str, network_name: str) -> Identity: ...

    # Room
    async def room_create(self, name: str) -> Room: ...
    async def room_invite(self, room: str, invitee: str) -> None: ...
    async def room_leave(self, room: str) -> None: ...
    async def rooms(self) -> list[Room]: ...
    async def members(self, room: str) -> list[Identity]: ...

    # Event 发布/订阅
    async def publish(self, event: ZChatEvent) -> None: ...
    async def subscribe(self, room: str) -> AsyncIterator[ZChatEvent]: ...

    # Event Store 查询
    async def query_events(self, room: str, last: int = 10,
                           since: str = None,
                           content_types: list[str] = None) -> list[ZChatEvent]: ...
    async def get_event(self, event_id: str) -> ZChatEvent | None: ...

    # 存储标记（用于 Extension 回扫）
    async def is_handled(self, event_id: str, handler_name: str) -> bool: ...
    async def mark_handled(self, event_id: str, handler_name: str) -> None: ...

    # 诊断
    async def doctor(self) -> DiagnosticReport: ...

    # 配置
    async def load_agent_config(self, name: str) -> SpawnConfig: ...
    async def load_template_config(self, name: str) -> SpawnConfig: ...
```

### 2.2 AcpBackend Protocol

```python
class AcpBackend(Protocol):
    """适配层接口——cli 不关心底层是 CC headless 还是 Gemini CLI"""

    # Spawn
    async def prepare_spawn(self, config: SpawnConfig) -> SpawnPreview: ...
    async def confirm_spawn(self, preview: SpawnPreview) -> SessionInfo: ...
    async def cancel_spawn(self, preview: SpawnPreview) -> None: ...

    # Session 管理
    async def sessions(self) -> list[SessionInfo]: ...
    async def get_session(self, agent_id: str) -> SessionInfo: ...
    async def kill_session(self, agent_id: str, force: bool = False) -> None: ...

    # 消息注入（模型 2：被动路由）
    async def inject_message(self, session_id: str, enriched_content: str) -> None: ...

    # 输出捕获（模型 2：被动路由）
    async def capture_output(self, session_id: str) -> AsyncIterator[ZChatOperation]: ...

    # attach/detach（人类直接交互）
    async def attach(self, agent_id: str) -> str: ...      # returns CC session ID
    async def detach(self, agent_id: str) -> None: ...

    # 状态
    async def get_status(self, session_id: str) -> SessionStatus: ...
```

### 2.3 组装

```python
# zchat/__main__.py
from zchat_cli import ZChatCLI
from zchat_com import ZenohComBackend      # 具体实现
from zchat_acp import HeadlessAcpBackend   # 具体实现

com = ZenohComBackend()
acp = HeadlessAcpBackend()
cli = ZChatCLI(com=com, acp=acp)
await cli.start()
```

**为什么这样设计**：
- 替换 Zenoh → 只需新的 ComBackend，cli 不变
- 支持新 Agent backend → 只需新的 AcpBackend，cli 不变
- Phase 0 mock → MockComBackend + MockAcpBackend 实现同样的 Protocol
- Extension = 新的 cli 操作 + 可能的 Backend 增强

---

## 3. 操作语义

cli 定义的每个操作都有明确的语义——不依赖具体 Backend 实现。

### 3.1 send

```
语义: 向目标发送消息
前置: 目标是有效的 Identity 或 Room
后置: 消息到达目标所在 Room 的所有成员
```

```python
async def send(self, target: str, content: str) -> Message:
    event = ZChatEvent(
        type="msg", from_=self.identity, room=resolve_room(target),
        content={"text": content, "mentions": extract_mentions(content)}
    )
    await self.com.publish(event)
    return event
```

### 3.2 watch

```
语义: 实时查看 Room 消息流，可选历史前缀
前置: Room 存在
后置: 输出消息流（follow 模式）或输出后退出（no-follow 模式）
```

```python
async def watch(self, room=None, last=10, no_follow=False, **filters):
    # 先输出历史
    events = await self.com.query_events(room=room, last=last)
    for event in events:
        yield self._format_event(event, **filters)
    # 再实时
    if not no_follow:
        async for event in self.com.subscribe(room):
            yield self._format_event(event, **filters)
```

### 3.3 ask / answer

```
语义: 向目标发起阻塞式提问，等待回答
前置: 目标在线或可收到消息
后置: 收到 answer 后返回，超时后报错
```

```python
async def ask(self, target: str, question: str, timeout: int = 1800) -> str:
    ask_event = ZChatEvent(
        type="ask", from_=self.identity,
        room=resolve_room(target),
        content={"question": question, "target": target}
    )
    await self.com.publish(ask_event)
    try:
        answer = await asyncio.wait_for(
            self._wait_for_answer(ask_event.id), timeout=timeout
        )
        return answer.content["text"]
    except asyncio.TimeoutError:
        raise AskTimeoutError(f"{target} 未在 {timeout}s 内回复")

async def answer(self, ask_id: str = None, text: str = "") -> None:
    if ask_id is None:
        ask_id = await self._find_latest_pending_ask()
    answer_event = ZChatEvent(
        type="answer", from_=self.identity,
        replyTo=ask_id, content={"text": text}
    )
    await self.com.publish(answer_event)
```

### 3.4 spawn

```
语义: 启动一个 Agent 实例
前置: 配置文件存在（agent TOML 或 template）
后置: Agent 以 AFK headless 模式运行，加入指定 Room
```

```python
async def spawn(self, agent_name: str, resume: bool = False) -> SpawnPreview:
    config = await self.com.load_agent_config(agent_name)
    preview = await self.acp.prepare_spawn(config)
    return preview

async def spawn_confirm(self, preview: SpawnPreview) -> SessionInfo:
    session = await self.acp.confirm_spawn(preview)
    await self.com.publish(ZChatEvent(
        type="join", from_=session.identity,
        room=session.default_room
    ))
    return session
```

### 3.5 session attach / detach

```
语义: 暂停 Agent headless 进程，让人类直接在 CC TUI 中交互
前置: Agent 正在运行，调用者是 Owner
后置: attach → headless 暂停 + 输出 session ID；detach → 恢复 + 回扫
```

```python
async def session_attach(self, agent_id: str) -> str:
    session = await self.acp.get_session(agent_id)
    self._check_owner(session)
    cc_session_id = await self.acp.attach(agent_id)
    return cc_session_id  # 人类用此 ID 执行 claude --resume

async def session_detach(self, agent_id: str) -> None:
    await self.acp.detach(agent_id)
    # detach 内部自动回扫 attach 期间积累的 @mention 消息
```

### 3.6 doctor

```
语义: 诊断 zchat 运行环境
前置: 无
后置: 输出诊断报告
```

```python
async def doctor(self) -> DiagnosticReport:
    return await self.com.doctor()
```

---

## 4. Python API（完整接口）

```python
class ZChatCLI:
    def __init__(self, com: ComBackend, acp: AcpBackend): ...

    # 生命周期
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    # 事件订阅
    def on_message(self, cb) -> None: ...
    def on_session_update(self, cb) -> None: ...
    def on_permission_request(self, cb) -> None: ...

    # Identity + Network
    async def get_identity(self) -> Identity: ...
    async def get_network(self) -> NetworkInfo: ...
    async def get_peers(self) -> list[Identity]: ...

    # Room
    async def room_create(self, name: str) -> Room: ...
    async def room_invite(self, room: str, invitee: str) -> None: ...
    async def room_leave(self, room: str) -> None: ...
    async def rooms(self) -> list[Room]: ...
    async def members(self, room: str) -> list[Identity]: ...

    # Message
    async def send(self, target: str, content: str) -> Message: ...

    # Watch
    async def watch(self, room: str = None, last: int = 10,
                    no_follow: bool = False, verbose: bool = False,
                    thinking: bool = False, show_all: bool = False,
                    from_participant: str = None, json_mode: bool = False,
                    since: str = None) -> AsyncIterator[ZChatEvent]: ...

    # Ask/Answer
    async def ask(self, target: str, question: str, timeout: int = 1800) -> str: ...
    async def answer(self, ask_id: str = None, text: str = "") -> None: ...

    # Template + Agent 管理
    async def template_init(self, name: str) -> Path: ...
    async def template_list(self) -> list[TemplateInfo]: ...
    async def agent_init(self, name: str, from_template: str) -> Path: ...
    async def agent_list(self) -> list[AgentConfigInfo]: ...

    # Spawn
    async def spawn(self, agent_name: str, resume: bool = False) -> SpawnPreview: ...
    async def spawn_adhoc(self, template: str, name: str) -> SpawnPreview: ...
    async def spawn_confirm(self, preview: SpawnPreview) -> SessionInfo: ...
    async def spawn_cancel(self, preview: SpawnPreview) -> None: ...

    # Session
    async def status(self, session_id: str = None) -> SessionStatus | NetworkStatus: ...
    async def sessions(self) -> list[SessionInfo]: ...
    async def session_attach(self, agent_id: str) -> str: ...
    async def session_detach(self, agent_id: str) -> None: ...
    async def kill(self, agent_id: str, force: bool = False) -> None: ...

    # 诊断
    async def doctor(self) -> DiagnosticReport: ...

    # Extension 管理
    async def ext_install(self, name: str) -> None: ...
    async def ext_uninstall(self, name: str) -> None: ...
    async def ext_list(self) -> list[ExtensionInfo]: ...
```

---

## 5. Shell 命令

```bash
# 无参数 → 启动长驻进程
zchat

# Template 管理
zchat template init <n>
zchat template list

# Agent 实例管理
zchat agent init <n> --from <template>
zchat agent list

# Spawn
zchat spawn <agent_name> [--resume] [--yes]
zchat spawn --template <t> --name <n> [--yes]

# Network + Room
zchat network
zchat peers
zchat rooms
zchat members <room>
zchat room create <n>
zchat room invite <room> <user>
zchat room leave <room>

# Message
zchat send <target> <message>

# Watch（替代 TUI + history）
zchat watch [room]                            # 实时 + 最近 10 条
zchat watch [room] --last <N>                 # 指定历史条数
zchat watch [room] --no-follow                # 输出后退出
zchat watch [room] --verbose                  # + tool_use/tool_result
zchat watch [room] --thinking                 # + thinking
zchat watch [room] --all                      # 不过滤
zchat watch [room] --from <participant>       # 只看某人
zchat watch [room] --json                     # 原始 JSON
zchat watch [room] --since "2h ago"           # 从指定时间

# Ask/Answer
zchat ask <target> "<question>" [--timeout 600]
zchat answer [ask-id] "<text>"

# Session
zchat status [session] [--json]
zchat sessions
zchat session attach <agent>
zchat session detach <agent>
zchat session kill <agent> [--force]

# 诊断
zchat doctor

# Extension 管理
zchat ext install <n>
zchat ext uninstall <n>
zchat ext list

# 前置检查
zchat preflight
```

Extension 通过 manifest 注册的 CLI 子命令自动可用（如 ext-migrate 安装后 `zchat session grant/reclaim` 可用）。

---

## 6. Agent Hook 脚本

zchat_inject 安装到 CC：

```bash
# ~/.claude/hooks/session-end.sh
#!/bin/bash
zchat session-end "$ZCHAT_SESSION_ID"

# ~/.claude/hooks/after-prompt.sh
#!/bin/bash
zchat status "$ZCHAT_SESSION_ID"
```

---

## 7. 前置检查

```
$ zchat preflight
✓ Python 3.12.3
✓ gh 2.45.0 (已登录: alice)
✓ claude (Claude Code v2.1.29)
✓ zenoh (检测 Zenoh daemon)
```

---

## 8. 边界

| 范围内 | 范围外 |
|---|---|
| 操作语义定义 | 传输实现 (com) |
| ComBackend / AcpBackend Protocol | Agent 进程管理 (acp) |
| Shell 命令 + Python API | Event Store 实现 (com) |
| Extension CLI 动态注册 | Annotation 附加逻辑 (com) |
| watch 显示过滤 | Enriched message 构造 (acp) |
| template/agent 配置管理 | TUI (推迟) |

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-protocol](./03-protocol.md) · [zchat-com](./04-com.md) · [zchat-acp](./05-acp.md)
- [Extension 机制](./06-extension.md) · [AgentSkill](./zchat.md) · [zchat-tui](./07-tui.md)
- [开发阶段](./09-dev-phases.md) · [E2E](./08-e2e-scenarios.md) · [MVP](./10-mvp-implementation.md) · [测试](./11-mvp-testcases.md)
