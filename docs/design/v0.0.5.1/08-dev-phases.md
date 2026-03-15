# 开发阶段规划 v0.0.5.1

---

## 设计原则

1. **每个阶段结束后，E2E A-H 全部可运行**——未完成的部分用完整 mock
2. **逐步替换 mock 为真实实现**
3. **最大化并行**——CC agent 执行所有 Track，无人数限制
4. **接口先行**——Phase 0 的 mock 接口 = 真实接口约定
5. **最终消除所有 mock**——Phase 4 验证系统中不存在 mock 功能模块

当前仅支持 Claude Code。

---

## 依赖图

```
zchat-protocol ──────────── 必须先完成（Phase 0）
       │                │
       ▼                ▼
  zchat-com         zchat-acp     ← 可并行
       │                │
       └───────┬────────┘
               ▼
          zchat-cli               ← 等 com + acp 接口
               │
               ▼
          zchat-tui               ← 等 cli 接口
```

---

## Phase 0：骨架 + 全 Mock E2E（1 周，1 agent）

> E2E A-H 全部可交互，全由 mock 驱动。接口锁定。

### 交付物

| 包 | 状态 |
|---|---|
| zchat-protocol | **真实**——全部原语 schema |
| zchat-com | 接口骨架 + mock（内存假数据） |
| zchat-acp | 接口骨架 + mock（假 session，固定回复） |
| zchat-cli | 完整路由 + 连接 mock |
| zchat-tui | 完整 UI + mock 数据 |
| tests | protocol 真实测试 + E2E smoke |
| configs/templates/ | 内置 template：coder.toml, reviewer.toml |

### Mock 要求

每个 mock 必须：
1. **实现真实接口**——签名完全一致
2. **返回合理假数据**——结构完整
3. **支持基本交互**——发消息得到回复，spawn 看到 session
4. **记录调用日志**

### Phase 0 后 E2E

A-H 全部可运行，数据全假。接口锁定，后续 Phase 只替换实现。

Mock E2E 体验：

```
$ uvx zchat
A. 身份: hardcoded alice@mocknet
B. zchat template init coder → mock 写 .zchat/templates/coder.toml
   zchat agent init ppt-maker --from coder → mock 写 .zchat/agents/ppt-maker.toml
   :spawn ppt-maker → 假 session → running
C. Chat @ppt-maker → 假回复
D. :afk → 状态切换
E. bob 假消息
F. :session grant → 日志 "would migrate"
G. 模拟离线 → 假消息补回
H. :session kill → session 消失
```

---

## Phase 1：真实核心（2 周，5 Track 并行）

> A-E 真实。F-H mock。

### Track 拓扑

```
Phase 0 完成
  ├→ Track α: zchat-com 核心
  ├→ Track β: zchat-acp 核心 (CC + tmux)
  ├→ Track γ: zchat-cli 真实连接     ← Week 2
  ├→ Track δ: zchat-tui 打磨         ← Week 2
  └→ Track ε: 集成测试               ← Week 2 后半
```

### Track α：zchat-com（CC agent #1）

测试：mock acp peer

| Week | 内容 |
|---|---|
| 1 | identity (gh auth), network (创建/发现), room (CRUD + 成员 + SystemEvent), message_router (路由 + Index + Hook OnRoute), config (template/agent 目录管理 + inherits 解析) |
| 2 | presence (心跳 + peer), Annotation 附加 (priority per-recipient + injection_path), inject (读 Annotation), 基本 Timeline |

### Track β：zchat-acp（CC agent #2）

测试：mock com peer

| Week | 内容 |
|---|---|
| 1 | server.py (Zenoh 订阅 + Message 解析), spawn.py (4-phase + SpawnConfig 加载含 inherits + Hook 注册), tmux/bridge.py (send_keys + capture_pane), Hook 调度 (registry + trigger→handler) |
| 2 | tmux/output_parser.py (on_output: 分类 + Room 发布), access.py (human/zchat mode + owner/operator 基础), tmux/agents/cc.py (patterns + zchat_inject), Hook(session_end, after_prompt) 的 shell 脚本生成 |

### Track γ：zchat-cli（CC agent #3，Week 2）

替换 mock import → 真实 com/acp。preflight。CLI 子命令（afk, back, status, send, rooms, sessions）。template init/list + agent init/list 真实化。

### Track δ：zchat-tui（CC agent #4，Week 2）

替换 mock cli → 真实 ZChatCLI。引导流程真实化。headless 测试。

### Track ε：集成测试（CC agent #5，Week 2 后半）

E2E A-E 真实链路。多用户模拟。CI pytest。

### Phase 1 结束后

| 故事 | 状态 |
|---|---|
| A-E | ✅ 真实 |
| F-H | ⬜ mock |

---

## Phase 2：迁移 + 离线（2 周，4 Track 并行）

> F-H 真实。E2E 全部真实。

### Track 拓扑

```
Phase 1 完成
  ├→ Track ζ: store (outbox/relay/inbox)
  ├→ Track η: migrate + access 完整
  ├→ Track θ: sync + Timeline gap     ← Week 2 连接 ζ
  └→ Track ι: TUI 迁移/离线 UI        ← Week 2
```

### Track ζ：store（CC agent #1）

| Week | 内容 |
|---|---|
| 1 | store/outbox.py (目标离线→JSONL + RelayRequest), store/relay.py (接收→副本), store/inbox.py (queryable→写入) |
| 2 | replication 管理, DeliveryConfirm → 清理 outbox+relay, TTL |

### Track η：migrate + access（CC agent #2）

| Week | 内容 |
|---|---|
| 1 | migrate.py (Hook on_migrate_out: bundle 打包, on_migrate_in: 接收+spawn+resume), access.py 完整 (owner/operator/observer + grant 权限) |
| 2 | reclaim (取消订阅 + AfterPromptSend hook), SessionEnd hook (CLI bundle-return → outbox), zchat_inject 完善 (system hook 安装), --resume |

### Track θ：sync + Timeline（CC agent #3）

| Week | 内容 |
|---|---|
| 1 | sync.py (queryable + merge + dedup), Timeline gap 检测 + fill_gaps() |
| 2 | 连接 store/ 读取, Annotation(offline_gap), 离线消息标注 |

### Track ι：TUI 迁移/离线（CC agent #4，Week 2）

迁移确认/Reclaim 确认/Bundle 通知/关闭安全对话框。离线标注渲染。Agent 5 种状态。

### Phase 2 结束后

| 故事 | 状态 |
|---|---|
| A-H | ✅ 全部真实 |

**→ 单机可用。**

---

## Phase 3：LAN + 打磨（2 周）

| 内容 | 说明 |
|---|---|
| LAN 跨机器 | Zenoh multicast 测试 + 调优 + 多机 E2E |
| OutputParser 增强 | tool_call + permission 检测 |
| Session Tab 交互 | Ctrl+E 完善 + 5 分钟超时 |
| TUI 打磨 | 对话框细节、快捷键、TOML theme |
| 文档 | README + 安装指南 + 贡献指南 |

---

## Phase 4：Mock 消除验证

> **目标**：确认系统中不再存在 mock 功能模块。所有测试使用真实 API 调用，仅 test fixtures（数据）是构造的。

### 4.1 代码审计

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
| zchat-acp | mock session / mock tmux 已删除 | 所有方法操作真实 tmux |
| zchat-cli | mock com/acp import 已替换 | 所有方法调用真实 com + acp |
| zchat-tui | mock cli 已替换 | 所有命令调用真实 ZChatCLI |

### 4.2 测试审计

```
扫描 tests/:
  每个测试文件检查: 是否使用真实 API 调用？
  允许: test fixtures（构造的假数据）
  不允许: mock 掉整个模块（如 @mock.patch("zchat_com.message_router")）
```

| 测试类别 | 允许的 mock | 不允许的 mock |
|---|---|---|
| protocol 测试 | 无需 mock | — |
| com 测试 | Zenoh test session (真实 Zenoh 但隔离网络) | mock 掉 message_router 或 store |
| acp 测试 | 真实 tmux (tmux -L zchat-test) | mock 掉 tmux_bridge 或 output_parser |
| cli 测试 | 真实 com + acp (可以是 localhost Zenoh) | mock 掉 com 或 acp 模块 |
| tui 测试 | Textual headless + 真实 cli | mock 掉 cli |
| 集成测试 | 仅 test fixtures (构造的消息、配置) | 不允许任何模块 mock |

### 4.3 E2E 全真实验证

```
运行完整 E2E A-H:
  - 真实 Zenoh (localhost)
  - 真实 tmux
  - 真实 Claude Code (使用 --dangerously-skip-permissions 或 test API key)
  - 多用户通过多 Zenoh session 模拟

每个 E2E 场景必须:
  ✅ 使用真实 zchat CLI 命令
  ✅ 使用真实 Zenoh 消息传递
  ✅ 使用真实 tmux 操作
  ✅ 仅 test fixtures 是构造的（用户名、房间名、消息内容）
```

### 4.4 交付物

- Mock 消除报告（每个包的检查结果）
- 测试覆盖率报告
- E2E 全真实测试通过截图/日志
- Phase 0 的 mock 代码从代码库中删除（或移入 `tests/fixtures/`）

---

## 并行时间线

```
Week:  1         2         3         4         5         6         7
       ├─────────┤─────────┤─────────┤─────────┤─────────┤─────────┤

P0:    ██████████                                                    1 agent
       protocol + skeleton + mock E2E

P1:              ████████████████████                                5 agents
       α(com):   ──────────────────
       β(acp):   ──────────────────
       γ(cli):        ─────────────
       δ(tui):        ─────────────
       ε(integ):           ────────

P2:                        ████████████████████                      4 agents
       ζ(store):           ──────────────────
       η(migrate):         ──────────────────
       θ(sync):            ──────────────────
       ι(tui-ext):              ─────────────

P3:                                  ████████████████████            2-3 agents
                                     LAN + polish

P4:                                            ██████████            1 agent
                                               mock 消除验证

里程碑:
  Week 1 末: E2E A-H 可跑（mock）
  Week 3 末: E2E A-E 真实
  Week 5 末: E2E A-H 全部真实，单机可用
  Week 7 末: LAN 可用 + mock 消除确认
```

---

## CC Agent 工作方式

每个 Track 是独立 CC agent session，运行在自己的 git worktree：

```
zchat-mono/
├── worktree-alpha/    ← CC #1: zchat-com
├── worktree-beta/     ← CC #2: zchat-acp
├── worktree-gamma/    ← CC #3: zchat-cli
├── worktree-delta/    ← CC #4: zchat-tui
└── worktree-epsilon/  ← CC #5: integration

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
    sub = zenoh_session.declare_subscriber("zchat/acp/*/request")
    async for msg in sub:
        request = Message.deserialize(msg.payload)
        if request.content_type == "acp.session.new":
            response = Message(content=AcpPayload.response(session_id="mock-001"))
            zenoh_session.put("zchat/acp/mock-001/response", response.serialize())
```

---

## 相关文档

- [架构概览](./01-overview.md) · [E2E](./07-e2e-scenarios.md) · [测试](./10-mvp-testcases.md)
- [protocol](./02-protocol.md) · [com](./03-com.md) · [acp](./04-acp.md) · [cli](./05-cli.md) · [tui](./06-tui.md)
- [MVP 实现](./09-mvp-implementation.md)
