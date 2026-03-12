# MVP 测试用例 v0.0.5.1

---

## E2E 故事（44 场景）

A(4) · B(5) · C(5) · D(3) · E(3) · F(9) · G(11) · H(4)

详见 [E2E](./07-e2e-scenarios.md)。

---

## 底层测试

### zchat-protocol（10 个）

| ID | 原语 | 说明 |
|---|---|---|
| T-0.1 | DataType(AcpPayload) | JSON-RPC round-trip |
| T-0.2 | DataType(AcpPayload) | error 构造 |
| T-0.3 | Index | pattern 构造器 |
| T-0.4 | Message | round-trip（含 content_type） |
| T-0.5 | Identity | `user@network` 解析 |
| T-0.6 | Identity | `user:agent@network` 解析 |
| T-0.7 | DataType(MigrationBundle) | 序列化 |
| T-0.8 | Hook | 定义 round-trip（含 runtime） |
| T-0.9 | Annotation | per-recipient 序列化 |
| T-0.10 | Timeline | gap 填充逻辑 |

### zchat-com（26 个）

| ID | 原语 | 说明 |
|---|---|---|
| T-B.0 | DataType(SpawnConfig) | inherits 解析：agent TOML → template TOML → 默认值 |
| T-A.1 | Identity | gh auth 解析 |
| T-A.2 | Identity+Index | 网络创建+广播 |
| T-A.3 | Identity | 发现+加入 |
| T-A.4 | Identity | `user@network` 格式 |
| T-A.5 | Room+Index | peer+room 列表 |
| T-C.1 | Room | 创建+自动加入 |
| T-C.2 | Room+Message | 邀请+SystemEvent |
| T-C.5 | Annotation+Hook | 房间→agent, priority |
| T-C.6 | Message | SystemEvent 广播 |
| T-E.1 | Room | 人类加入 |
| T-E.2 | Annotation | 跨用户→agent CRITICAL |
| T-E.3 | Annotation | 广播多接收者 |
| T-E.4 | Annotation | 房间 agent NORMAL |
| T-G.1 | Message | offline 检测 |
| T-G.2 | Index(relay) | 写入 outbox |
| T-G.3 | store | RelayRequest 广播 |
| T-G.4 | store | 接收 relay 副本 |
| T-G.5 | Timeline | queryable+merge+dedup |
| T-G.6 | store | replication factor |
| T-G.7 | store | DeliveryConfirm 清理 |
| T-G.8 | Timeline | gap 填充 |
| T-G.9 | Annotation | offline_gap 标注 |
| T-G.10 | store | TTL 清理 |
| T-H.2 | Message | 离线广播 |
| T-H.5 | — | pending 消息 agent 恢复后 inject |

### zchat-acp（15 个）

| ID | 原语 | 说明 |
|---|---|---|
| T-1.1 | Index | Zenoh initialize |
| T-1.2 | — | 未知 method error |
| T-1.3 | Hook | tmux send-keys → capture-pane |
| T-1.4 | Hook(on_output) | OutputParser → Message |
| T-1.5 | Hook(on_idle) | idle → end_turn |
| T-B.1 | DataType(SpawnConfig) | config 加载 (inherits 解析合并 + hooks/skills/mcp) |
| T-B.2 | Hook | zchat_inject 安装 agent hook 脚本 |
| T-B.3 | Identity | `user:agent@network` 构造 |
| T-F.2 | Hook(on_migrate_out) | bundle 打包 |
| T-F.3 | DataType(MigrationBundle) | bundle 传输 |
| T-F.4 | Hook(on_migrate_in) | 接收+spawn+resume |
| T-F.6 | Hook | 非 owner grant 拒绝 |
| T-F.7 | Hook(after_prompt) | reclaim 脱网提示 |
| T-F.8 | Hook(session_end) | bundle 打包+回传 |
| T-H.1 | Room | 关闭前检查成员 |

### zchat-cli（9 个）

| ID | 说明 |
|---|---|
| T-CLI.1 | `zchat afk` → Zenoh → acp mode |
| T-CLI.2 | `zchat back` → 恢复 |
| T-CLI.3 | `zchat status --json` |
| T-CLI.4 | `zchat bundle-return` → outbox |
| T-CLI.5 | `zchat send` → 正确 Index |
| T-CLI.6 | `zchat preflight` |
| T-CLI.7 | `zchat spawn --yes` 跳过确认 |
| T-CLI.8 | `zchat template init` → 生成 .zchat/templates/ |
| T-CLI.9 | `zchat agent init --from` → 生成 .zchat/agents/ (含 inherits) |

### zchat-tui（5 个）

| ID | 说明 |
|---|---|
| T-3.1 | Textual headless 渲染 |
| T-3.2 | :spawn → cli.spawn() |
| T-3.3 | Session Tab 输出 |
| T-3.4 | 命令→CLI 映射 |
| T-3.5 | 对话框显示 |

---

## 统计

| 类别 | 数量 |
|---|---|
| E2E 场景 | 43 |
| protocol | 10 |
| com | 26 |
| acp | 15 |
| cli | 9 |
| tui | 5 |
| **底层合计** | **65** |
| **总计** | **109** |

---

## 测试基础设施

| 关注点 | 方案 |
|---|---|
| Zenoh 隔离 | `multicast.enabled=false` + 显式 endpoints |
| 多用户 | 多 Zenoh session（不同 Identity） |
| 真实 tmux | `tmux -L zchat-test` |
| Textual headless | `app.run(headless=True)` |
| 测试 agent | `cat` 或 echo script（非 Claude Code） |
| Hook 测试 | mock CC 进程 + 验证 hook 触发 |

### Phase 4 测试标准

- 生产代码中 0 个 mock 模块
- 测试中仅 fixtures（数据）是构造的
- 所有 API 调用是真实的（真实 Zenoh + 真实 tmux）
- 不允许 `@mock.patch` 掉整个模块

---

## 相关文档

- [架构概览](./01-overview.md) · [E2E](./07-e2e-scenarios.md) · [开发阶段](./08-dev-phases.md)
- [protocol](./02-protocol.md) · [com](./03-com.md) · [acp](./04-acp.md) · [cli](./05-cli.md) · [tui](./06-tui.md)
- [MVP 实现](./09-mvp-implementation.md)
