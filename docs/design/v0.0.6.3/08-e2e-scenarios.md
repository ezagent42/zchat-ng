# ZChat 完整 E2E 场景 v0.0.6.3

---

## 权限模型（v0.0.6.3 精简）

| 角色 | 权限 |
|---|---|
| **Owner** | spawn、kill、attach/detach |
| **Operator** | 独占交互（@mention → CC 响应） |

> **v0.0.6 变更**：移除 Observer 角色（推迟）。移除 grant/reclaim（→ ext-migrate）。MVP 中 Owner = Operator。

### 权限矩阵

| 操作 | Owner | Operator | Observer (推迟) |
|---|---|---|---|
| spawn / kill | ✅ | ❌ | ❌ |
| attach / detach | ✅ | ❌ | ❌ |
| @mention / send | ✅ | ✅ | ✅ |
| watch | ✅ | ✅ | ✅ |
| grant / reclaim (ext-migrate) | ✅ | ❌ | ❌ |

---

## Phase A：身份与网络（4 场景）

- **A1**: alice 首次启动 → gh auth login → 命名 "onesyn" → alice@onesyn
- **A2**: bob 启动 → Zenoh scout 发现 onesyn → 自动加入 → bob@onesyn
- **A3**: charlie 加入。3 人在线
- **A4**: `zchat status` 显示 3 个 peers；`zchat rooms` 显示 #general

## Phase B：Agent 创建（5 场景）

- **B1**: `zchat template init coder` → 生成 `.zchat/templates/coder.toml`（内置模板）→ alice 编辑：设置 program=claude, skills, mcp, hooks → git commit（团队共享）
- **B2**: `zchat agent init ppt-maker --from coder` → 生成 `.zchat/agents/ppt-maker.toml`（inherits="coder"）
- **B3**: `zchat spawn ppt-maker` → 加载 agent 配置（inherits 合并）→ workspace 准备（MCP 热加载 + Skills symlink）→ CC headless 启动（AFK 默认）→ alice:ppt-maker@onesyn 上线
- **B4**: `zchat spawn --template coder --name api-refactor` → 临时从 template 启动（不创建持久 agent 配置）
- **B5**: `zchat send @ppt-maker "请制作 Q3 PPT"` → adapter 构造 enriched message → JSONL stdin → CC 执行 → stdout → ZChatEvent(type=msg) → Room

## Phase C：房间与通信（5 场景）

- **C1**: `zchat room create #alice-workshop` → 自动加入
- **C2**: `zchat room invite #alice-workshop alice:ppt-maker` → SystemEvent(join) 广播
- **C3**: alice `zchat send #alice-workshop "开始做 PPT"` → ZChatEvent → Room → `zchat watch` 显示
- **C4**: CC headless 回复 → stdout → adapter → ZChatEvent(type=msg) → Room → `zchat watch` 显示。CC 的 thinking/tool_use 也广播到 Room，`zchat watch` 默认不显示，`--verbose` 或 `--thinking` 可查看
- **C5**: bob `zchat send @ppt-maker "配色要改"` → adapter enriched message（含上下文窗口 N=10/T=12h + replyTo 展开）→ JSONL stdin → CC 处理 → 回复到 Room

## Phase D：人类介入与交互（6 场景）

- **D1**: CC 执行中需要人类决策 → CC 原生 AskUserQuestion → adapter 拦截 → 转为 ZChatEvent(type=ask) 发到 Room → alice `zchat watch` 看到提问 → `zchat answer "slide.dev"` → adapter → JSONL stdin tool_result → CC 继续
- **D2**: CC 通过 AgentSkill 主动提问 → `tool_use: Bash("zchat ask @alice '封面要什么风格？'")` → ask event → alice `zchat answer "极简"` → CC tool_use 返回结果 → CC 继续
- **D3**: CC 通过 AgentSkill 主动查看上下文 → `tool_use: Bash("zchat watch #alice-workshop --last 50 --no-follow")` → 获取更多历史消息
- **D4**: `zchat session attach ppt-maker` → headless 暂停，输出 session ID → alice 在另一个终端 `claude --resume <id>` 直接交互 → 完成后 `zchat session detach ppt-maker` → headless 恢复 + 回扫 attach 期间积累的消息
- **D5**: CC 空闲 10 分钟 → 进程池回收（保留 sessionId）→ 下次 `zchat send @ppt-maker "..."` → adapter 用 `--resume` 恢复 → CC 继续
- **D6**: `zchat ask #alice-workshop "哪个方案更好？"` → Room 内任何成员可 answer → 先到先得 → 超时 30 分钟

## Phase E：多人协作（5 场景）

- **E1**: `zchat room invite #alice-workshop bob` → bob 收到 SystemEvent(join)
- **E2**: bob `zchat send @ppt-maker "第三页数据有误"` → adapter enriched message → CC 处理 → 回复到 Room → alice 和 bob 都在 `zchat watch` 中看到
- **E3**: bob `zchat send @alice "看一下设计稿"` → alice 在 `zchat watch` 中看到。ppt-maker 不被注入此消息（非 @mention，正确行为：节省 token，agent 只响应被直接叫到的消息）
- **E4** (Agent→Agent): ppt-maker CC 内 `tool_use: Bash("zchat send @data-cruncher '需要 Q3 数据'")` → Zenoh publish → data-cruncher adapter enriched message → data-cruncher 回复 → ppt-maker adapter 收到
- **E5** (Agent→Human): data-cruncher CC 内 `tool_use: Bash("zchat send @alice '数据准备好了'")` → alice 在 `zchat watch` 中看到

## Phase F：Session 迁移 — ext-migrate Extension 场景

> **整体移入 ext-migrate Extension，MVP 不实现。**

**Core 下的替代路径**：bob 不需要迁移 agent 进程就能与 ppt-maker 交互——bob 在自己终端 `zchat send @ppt-maker "..."` 即可（消息通过 Room 路由到 alice 机器上的 headless CC）。

以下场景在 ext-migrate 安装后可用：

- **F1**: bob `:session attach` → 只读
- **F2**: alice `zchat session grant ppt-maker bob` → 确认 → bundle 打包+传输 → bob spawn+resume → 广播
- **F3**: bob Ctrl+E → CC 拥有完整历史
- **F4**: 非 owner grant → 拒绝
- **F5**: alice `zchat session reclaim` → bob CC 脱网（Hook after_prompt 提示）
- **F6**: bob CC 继续本地运行，prompt 后 hook 提示"已脱网"
- **F7**: bob /exit → Hook(session_end) → bundle 回传（直接/outbox/relay）
- **F8**: alice `zchat spawn ppt-maker --resume` → 恢复
- **F9**: alice 丢弃 → session 关闭

## Phase G：离线与重连 — ext-offline Extension 场景 + Core 最小处理

> **完整离线同步移入 ext-offline Extension。Core 仅提供最小处理。**

**Core 最小离线处理**：
- **G-alt1**: alice 离线 → Zenoh 检测 → presence=offline → Room 广播 SystemEvent(offline)
- **G-alt2**: alice 重连 → Zenoh queryable backfill → 拉取离线期间的 Room events（简单补全，不保证完整）
- **G-alt3**: 如果补全不全 → `zchat watch #room --since "2h ago"` 手动查看

以下场景在 ext-offline 安装后可用：

- **G1**: alice 离线（agent 本机）→ 系统消息 + agent 离线。不可 takeover
- **G2**: alice 离线（agent 在 bob）→ agent 不受影响
- **G3**: 离线期间消息 → outbox + charlie relay
- **G4**: @agent pending → agent 恢复后 inject
- **G5**: alice 重连 → queryable → fill gaps → 标注"离线期间"
- **G6**: Agent 恢复 → CC 检查 → 恢复或提示 resume
- **G7**: bob /exit, alice 离线, charlie 在线 → outbox → relay → queryable
- **G8**: bob /exit, 所有人离线 → outbox 留存 → 后续传输
- **G9**: 团队消息 relay
- **G10**: replication factor 验证
- **G11**: relay 清理（DeliveryConfirm）

## Phase H：Session 关闭（2 场景）

- **H1**: `zchat session kill ppt-maker` → 如果 Room 中有其他人类成员 → CLI 警告 + 需要 `--force` → 关闭 + SystemEvent(closed)
- **H2**: Room 中无其他人类成员 → 直接关闭

---

## 状态机（v0.0.6.3）

```
zchat spawn → RUNNING(owner=alice, mode=afk, headless)
  ├ idle 10min → SUSPENDED(sessionId 保留) → 新消息 → RUNNING(--resume)
  ├ attach → ATTACHED(headless 暂停) → detach → RUNNING(--resume + 回扫)
  ├ alice 离线 → OFFLINE → 重连 → RECOVERING(queryable backfill) → RUNNING
  └ kill → CLOSED
```

> **v0.0.6 变更**：移除 MIGRATING、RECLAIMED、BUNDLE_SENT 状态（→ ext-migrate）。移除 Direct/AFK 模式切换（→ 推迟）。

---

## 数据同步总结（v0.0.6.3）

| 场景 | 机制 |
|---|---|
| zchat → CC (被动) | Room event → adapter enriched message → JSONL stdin |
| CC → Room (被动) | CC stdout → adapter → ZChatEvent → Zenoh publish |
| CC → zchat (主动) | CC tool_use: Bash("zchat send/ask/watch") → CLI 进程 → Zenoh publish |
| CC AskUserQuestion | CC 原生 ask → adapter → ask event → zchat answer → adapter → JSONL stdin |
| Agent → Agent | CC tool_use: Bash("zchat send @other-agent") → Zenoh → 对方 adapter |
| 人类直接交互 | attach → 暂停 headless → claude --resume → detach → 恢复 |
| 进程回收/恢复 | idle → terminate(保留 sessionId) → 新消息 → --resume |
| 简单离线补全 | Zenoh queryable backfill（Core 最小方案） |
| 完整离线同步 | outbox/relay/inbox（ext-offline） |
| Agent 迁移 | MigrationBundle 传输（ext-migrate） |

---

## E2E 场景统计

| Phase | 场景数 | 状态 |
|---|---|---|
| A (身份与网络) | 4 | Core |
| B (Agent 创建) | 5 | Core |
| C (房间与通信) | 5 | Core |
| D (人类介入与交互) | 6 | Core |
| E (多人协作) | 5 | Core |
| F (迁移) | 9 | ext-migrate |
| G (离线) | 3 (Core alt) + 11 (ext-offline) | 部分 Core |
| H (关闭) | 2 | Core |
| **Core 合计** | **30** | |

---

## 相关文档

- [架构概览](./01-overview.md) · [开发阶段](./09-dev-phases.md) · [测试用例](./11-mvp-testcases.md)
