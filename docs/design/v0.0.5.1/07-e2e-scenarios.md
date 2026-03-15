# ZChat 完整 E2E 场景 v0.0.5.1

---

## 权限模型

| 角色 | 权限 |
|---|---|
| **Owner** | grant、reclaim、kill |
| **Operator** | 独占交互、AFK；不能 grant 或 kill |
| **Observer** | 只读 |

规则：只有 Owner 能 grant（不可 chain-grant）；Owner 随时 reclaim；只有 Owner 能 kill；无 grant 不可 takeover；/exit → SessionEnd hook → bundle 经 outbox/relay 回传。

---

## Phase A：身份与网络（4 场景）

- **A1**: alice 首次启动 → gh auth login → 命名 "onesyn" → alice@onesyn
- **A2**: bob 启动 → 发现 onesyn → 自动加入 → bob@onesyn
- **A3**: charlie 加入。3 人在线，#general + #daily-news
- **A4**: 侧边栏正确显示 Peers 3 人、Rooms 2 个

## Phase B：Agent 创建（5 场景）

- **B0**: alice 创建角色模板 `zchat template init coder` → 生成 `.zchat/templates/coder.toml`（内置模板）→ alice 编辑：设置 program=claude, skills=superpowers+skill-creator, mcp=context7, hooks=check-preToolUse.sh → git commit（团队共享）
- **B1**: alice 从模板创建 agent 实例 `zchat agent init ppt-maker --from coder` → 生成 `.zchat/agents/ppt-maker.toml`（inherits="coder"）→ alice 可进一步编辑或直接使用
- **B2**: `:spawn ppt-maker` → 加载 agent 配置（解析 inherits → 合并 template）→ 显示摘要确认
- **B3**: Y 确认 → 4-phase spawn → tmux + CC 启动 → alice:ppt-maker@onesyn 上线；N → 不创建
- **B4**: 同一 template 启动多个独立 agent：`:spawn --template coder --name api-refactor` → alice:api-refactor@onesyn（临时从 template 启动，不创建持久 agent 配置文件）

## Phase C：房间与 CC↔zchat 同步（5 场景）

- **C1**: `:room create #alice-workshop` → 自动加入
- **C2**: `:room invite #alice-workshop alice:ppt-maker` → 系统消息
- **C3**: alice 在 CC 输入 → OutputParser 捕获 → 房间出现 alice 发的消息
- **C4**: CC 回复 → OutputParser end_turn → 房间出现 ppt-maker 的消息
- **C5**: bob @ppt-maker → inject 按 priority + access mode → CC 收到

## Phase D：AFK（3 场景）

- **D1**: CC 内 `/zchat afk`（bash tool 调用 `zchat afk`）→ mode 切换 → Session Tab 只读
- **D2**: alice Chat Tab @ppt-maker → send-keys → CC → 回复同步
- **D3**: `/zchat back` → mode 恢复

## Phase E：多人协作（3 场景）

- **E1**: `:room invite #alice-workshop bob` → bob 收到通知
- **E2**: bob @ppt-maker → CC 收到 + 回复到 CC session + 房间
- **E3**: bob @alice（人类）→ ppt-maker 在同一房间按 NORMAL 也收到

## Phase F：Session 迁移（9 场景）

- **F1**: bob `:session attach` → 只读
- **F2**: alice `:session grant ppt-maker bob` → 确认 → bundle 打包+传输 → bob spawn+resume → 广播
- **F3**: bob Ctrl+E → CC 拥有完整历史
- **F4**: 非 owner grant → 拒绝
- **F5**: alice `:session reclaim` → bob CC 脱网（Hook after_prompt 提示）
- **F6**: bob CC 继续本地运行，prompt 后 hook 提示"已脱网"
- **F7**: bob /exit → Hook(session_end) → bundle 回传（直接/outbox/relay）
- **F8**: alice `:spawn ppt-maker --resume` → 恢复
- **F9**: alice 丢弃 → session 关闭

## Phase G：离线与重连（11 场景）

- **G1**: alice 离线（agent 本机）→ 系统消息 + agent 离线。不可 takeover
- **G2**: alice 离线（agent 在 bob）→ agent 不受影响
- **G3**: 离线期间消息 → outbox + charlie relay
- **G4**: @agent pending → agent 恢复后 inject
- **G5**: alice 重连 → queryable → fill gaps → TUI 标注"离线期间"
- **G6**: Agent 恢复 → tmux/CC 检查 → 恢复或提示 resume
- **G7**: bob /exit, alice 离线, charlie 在线 → outbox → relay → queryable
- **G8**: bob /exit, 所有人离线 → outbox 留存 → 后续传输
- **G9**: 团队消息 relay
- **G10**: replication factor 验证
- **G11**: relay 清理（DeliveryConfirm）

## Phase H：Session 关闭（4 场景）

- **H1**: Owner 本地 /exit + 有房间成员 → 确认 → 关闭 + 广播
- **H2**: 无成员 → 直接关闭
- **H3**: Operator /exit → Hook(session_end) → bundle 回传（不阻止）
- **H4**: Operator 不能 kill

---

## 权限矩阵

| 操作 | Owner | Operator | Observer |
|---|---|---|---|
| spawn / kill | ✅(仅 operator 时) | ❌ | ❌ |
| grant / reclaim | ✅(条件) | ❌ | ❌ |
| Ctrl+E / afk | ✅ 仅 operator | ✅ | ❌ |
| /exit | ✅ → 关闭 | ✅ → SessionEnd hook | — |
| attach / @mention | ✅ | ✅ | ✅ |

---

## 状态机

```
:spawn → RUNNING(owner=operator=alice)
  ├ grant bob → MIGRATING → RUNNING(operator=bob)
  │   ├ reclaim → RECLAIMED(bob CC 脱网) → bob /exit → BUNDLE_SENT
  │   └ bob /exit → BUNDLE_SENT
  │       → alice resume → RUNNING / alice kill → CLOSED
  ├ alice 离线 → OFFLINE → 重连 → RECOVERING → RUNNING
  └ alice /exit → CLOSED
```

---

## 数据同步总结

| 场景 | 机制 |
|---|---|
| CC 输入/输出 → 房间 | Hook(on_output) → Message 到 Room Index |
| 房间 → CC | Hook(on_route) → Annotation → send-keys |
| grant | MigrationBundle 传输 |
| bob /exit → alice | SessionEnd hook → outbox/relay |
| 离线消息 | outbox → relay → queryable |
| reclaim | 脱网 Hook(after_prompt) |
| relay 清理 | DeliveryConfirm |

---

## 相关文档

- [架构概览](./01-overview.md) · [开发阶段](./08-dev-phases.md) · [测试用例](./10-mvp-testcases.md)
