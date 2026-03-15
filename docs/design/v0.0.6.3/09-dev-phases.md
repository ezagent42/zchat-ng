# 开发阶段规划 v0.0.6.3

---

## 设计原则

1. **每个阶段结束后，Core E2E A-E + G-alt + H 全部可运行**——未完成的部分用完整 mock
2. **逐步替换 mock 为真实实现**
3. **最大化并行**——CC agent 执行所有 Track，无人数限制
4. **接口先行**——Phase 0 的 mock 接口 = 真实接口约定
5. **最终消除所有 mock**——Phase 3 验证系统中不存在 mock 功能模块

当前仅支持 Claude Code。

---

## 依赖图

```
zchat-cli ────────── 核心层，Phase 0 锁定 Backend 接口
       │
       ▼
zchat-protocol ──── Phase 0 锁定类型定义
       ▲                ▲
       │                │
  zchat-com         zchat-acp     ← 可并行，实现 Backend 接口
```

> **v0.0.6.3 变更**：依赖反转。Phase 0 锁定的是 cli 定义的 ComBackend / AcpBackend Protocol，不是 com/acp 内部实现。

---

## Phase 0：骨架 + 全 Mock E2E（1 周，1 agent）

> Core E2E 全部可交互，全由 mock 驱动。接口锁定。

### 交付物

| 包 | 状态 |
|---|---|
| zchat-cli | **真实**——操作语义 + ComBackend / AcpBackend Protocol 定义（**接口锁定**）+ Shell 命令路由 + 连接 Mock Backend |
| zchat-protocol | **真实**——全部原语 schema（含 View、ref/fold、ExtensionManifest） |
| zchat-com | MockComBackend（内存 Event Store，本地回环路由）|
| zchat-acp | MockAcpBackend（headless adapter mock，固定回复）|
| zchat.md | AgentSkill 初稿 |
| tests | protocol 真实测试 + cli 真实测试 + E2E smoke |
| configs/templates/ | 内置 template：coder.toml, reviewer.toml |

### Mock 要求

每个 mock 必须：
1. **实现真实接口**——签名完全一致
2. **返回合理假数据**——结构完整
3. **支持基本交互**——发消息得到回复，spawn 看到 session
4. **记录调用日志**

### Phase 0 后 E2E

Mock E2E 体验：

```
$ zchat doctor                              → mock: Zenoh OK, peers: 0
$ zchat status                              → mock: no active sessions
$ zchat spawn ppt-maker                     → mock session (AFK)
$ zchat send @ppt-maker "做一个 Q3 PPT"     → mock reply
$ zchat watch #general                      → 最近 10 条 mock 消息 + 实时流式
$ zchat watch #general --verbose            → + tool_use/tool_result
$ zchat ask @mock-user "slide.dev?"         → mock answer (3 秒后)
$ zchat ext list                            → (empty)
$ zchat session attach ppt-maker            → mock: session ID + 提示
```

---

## Phase 1：真实 Core（2 周，3 Track 并行）

> A-E + G-alt + H 真实。F 和完整 G 为 Extension 场景。

### Track 拓扑

```
Phase 0 完成（cli 接口锁定 + Mock Backend）
  ├→ Track α: zchat-com (implements ComBackend)
  ├→ Track β: zchat-acp (implements AcpBackend)
  └→ Track γ: zchat-cli 真实 Backend 注入 + Extension 机制
```

### Track α：zchat-com（CC agent #1）

测试：mock acp peer

| Week | 内容 |
|---|---|
| 1 | identity (gh auth), network (创建/发现), room (CRUD + 成员 + SystemEvent), presence |
| 2 | event_router (Zenoh pub/sub + 宽容路由 + Annotation 附加), Event Store (JSONL 持久化), 简单 queryable backfill, config (template/agent 目录管理 + inherits 解析) |

### Track β：zchat-acp（CC agent #2）

测试：mock com peer

| Week | 内容 |
|---|---|
| 1 | headless adapter (CC JSONL I/O), enriched message 构造 ([zchat] 格式 + N=10/T=12h + replyTo 展开), spawn (4-phase + SpawnConfig + zchat_inject), workspace (MCP 热加载 + Skills symlink) |
| 2 | pool (idle 回收 + resume), access 基础 (Owner/Operator), attach/detach, CC stdout 全量广播 (msg/thinking/tool_use/tool_result → Room), CC 原生 AskUserQuestion adapter 处理 |

### Track γ：zchat-cli + Extension 机制（CC agent #3）

| Week | 内容 |
|---|---|
| 1 | 替换 mock → 真实 com/acp, send/rooms/members/spawn/status 真实化 |
| 2 | watch (Zenoh subscribe + 过滤 + --no-follow), ask/answer (pub + subscribe block), doctor (Zenoh 诊断), session attach/detach, ExtensionRegistry (热加载 + 回扫), ext install/uninstall/list |

### Phase 1 结束后

| 故事 | 状态 |
|---|---|
| A-E | ✅ 真实 |
| G-alt (Core 最小离线) | ✅ 真实 |
| H | ✅ 真实 |
| F (迁移) | ⬜ ext-migrate（未实现） |
| G (完整离线) | ⬜ ext-offline（未实现） |

---

## Phase 2：LAN 多机 + 打磨（1 周）

| 内容 | 说明 |
|---|---|
| LAN 跨机器 | Zenoh multicast 测试 + 调优 + 多机 E2E |
| zchat doctor | 完善多机诊断 |
| Agent→Agent | ppt-maker zchat send @data-cruncher 验证 |
| Edge case | CC 进程 crash recovery, Zenoh 断线重连 |
| AgentSkill | 基于真实使用调整措辞 |
| 文档 | README + 安装指南 |

---

## Phase 3：Mock 消除验证（2-3 天）

> **目标**：确认系统中不再存在 mock 功能模块。所有测试使用真实 API 调用，仅 test fixtures（数据）是构造的。

### 3.1 代码审计

```
扫描所有包:
  grep -r "mock" --include="*.py" packages/ | grep -v test | grep -v __pycache__

期望结果: 0 匹配（生产代码中无 mock）
```

逐包确认：

| 包 | 检查项 | 标准 |
|---|---|---|
| zchat-protocol | 无 mock（Phase 0 就是真实的） | ✅ 已确认 |
| zchat-com | core.py 中 MockZChatCore 已删除 | 所有方法调用真实 Zenoh |
| zchat-acp | mock session / mock headless 已删除 | 所有方法操作真实 CC headless |
| zchat-cli | mock com/acp import 已替换 | 所有方法调用真实 com + acp |

### 3.2 测试审计

| 测试类别 | 允许的 mock | 不允许的 mock |
|---|---|---|
| protocol 测试 | 无需 mock | — |
| com 测试 | Zenoh test session (真实 Zenoh 但隔离网络) | mock 掉 event_router 或 store |
| acp 测试 | MockClaudeProcess（模拟 JSONL 协议） | mock 掉 headless adapter |
| cli 测试 | 真实 com + acp (localhost Zenoh) | mock 掉 com 或 acp 模块 |
| 集成测试 | 仅 test fixtures (构造的消息、配置) | 不允许任何模块 mock |

### 3.3 E2E 全真实验证

```
运行完整 E2E A-E + G-alt + H:
  - 真实 Zenoh (localhost)
  - 真实 Claude Code headless subprocess (AFK Mode)
  - 多用户通过多 Zenoh session 模拟
  - Agent→Agent 通信验证
  - ask/answer 全链路
  - attach/detach 全链路
  - Extension 热加载机制

每个 E2E 场景必须:
  ✅ 使用真实 zchat CLI 命令
  ✅ 使用真实 Zenoh 消息传递
  ✅ 使用真实 CC headless 或 MockClaudeProcess
  ✅ 仅 test fixtures 是构造的
```

### 3.4 交付物

- Mock 消除报告（每个包的检查结果）
- 测试覆盖率报告
- E2E 全真实测试通过日志
- Phase 0 的 mock 代码从代码库中删除（或移入 `tests/fixtures/`）

---

## 并行时间线

```
Week:  1         2         3         4
       ├─────────┤─────────┤─────────┤──┤

P0:    ██████████                         1 agent
       protocol + skeleton + mock E2E

P1:              ████████████████████     3 agents
       α(com):   ──────────────────
       β(acp):   ──────────────────
       γ(cli):   ──────────────────

P2:                        ██████████     1-2 agents
                           LAN + polish

P3:                                 ███   1 agent
                                    验证

里程碑:
  Week 1 末: 所有 CLI 可跑（mock）
  Week 3 末: 单机 E2E 真实，Agent 双向通信
  Week 4 中: LAN 可用，mock 消除确认
```

---

## CC Agent 工作方式

每个 Track 是独立 CC agent session，运行在自己的 git worktree：

```
zchat-mono/
├── worktree-alpha/    ← CC #1: zchat-com
├── worktree-beta/     ← CC #2: zchat-acp
└── worktree-gamma/    ← CC #3: zchat-cli + extension

每个 agent 的 CLAUDE.md:
  - Track 任务清单
  - 接口约定（Phase 0 锁定）
  - mock peer 使用方式
  - 测试要求
```

Phase 切换时合并到 main，重新分配。

---

## Mock 策略

### Phase 0 Mock 要求

```python
class MockZChatCore(ZChatCoreInterface):
    def send_message(self, target, content):
        log.info(f"[MOCK] send: {target} <- {content}")
        asyncio.get_event_loop().call_later(1.0, lambda:
            self._emit_message(Message(
                sender=Identity(user="mock-agent", agent=target.agent, network="mocknet"),
                content=TextContent(f"Mock reply to: {content}"),
            ))
        )
```

### Phase 1+ Mock Peer

Track 独立开发时用 Zenoh mock peer 测试：

```python
async def mock_acp_peer(zenoh_session):
    sub = zenoh_session.declare_subscriber("zchat/room/*/events")
    async for msg in sub:
        event = ZChatEvent.deserialize(msg.payload)
        if event.type == "msg" and "@mock-agent" in event.content.get("text", ""):
            response = ZChatEvent(
                type="msg", from_="mock-agent@mocknet",
                room=event.room, content={"text": f"Mock reply to: {event.content['text']}"}
            )
            zenoh_session.put(f"zchat/room/{event.room}/events", response.serialize())
```

AFK Mode mock（模拟 CC headless subprocess）：

```python
class MockClaudeProcess:
    """模拟 CC headless JSONL 协议，用于 Track β 独立测试"""
    async def exchange(self, text: str) -> AsyncGenerator[CueEvent]:
        yield {"type": "system", "subtype": "init", "session_id": "mock-sess", "model": "mock"}
        yield {"type": "assistant", "message": {"content": [
            {"type": "text", "text": f"Mock reply to: {text}"}
        ]}}
        yield {"type": "result", "result": f"Mock reply to: {text}",
               "session_id": "mock-sess", "cost_usd": 0, "duration_ms": 100}
```

---

## 相关文档

- [架构概览](./01-overview.md) · [E2E](./08-e2e-scenarios.md) · [测试](./11-mvp-testcases.md)
- [protocol](./03-protocol.md) · [com](./04-com.md) · [acp](./05-acp.md) · [cli](./02-cli.md)
- [MVP 实现](./10-mvp-implementation.md) · [Extension 机制](./06-extension.md)
