# MVP 实现设计 v0.0.5.1

---

## 1. 包依赖

```
zchat-protocol:  无依赖
zchat-com:       → zchat-protocol
zchat-acp:       → zchat-protocol
zchat-cli:       → zchat-com + zchat-acp
zchat-tui:       → zchat-cli
```

当前仅支持 Claude Code (tmux backend)。

## 2. 原语 → 模块映射

| 原语 | 定义在 (protocol) | 实现在 |
|---|---|---|
| DataType | `datatypes/*.py` | 所有包 |
| Hook | `hook.py` | acp: `server.py`(调度), `spawn.py`(注册) |
| Annotation | `annotation.py` | com: `message_router.py`(附加) |
| Index | `index.py` | com: `message_router.py`(路由), acp: `server.py`(订阅) |
| Identity | `identity.py` | com: `identity.py`, `network.py` |
| Room | — | com: `room.py` |
| Message | `message.py` | com: `message_router.py`, cli: 构造 |
| Timeline | `timeline.py` | com: `sync.py`, tui: 渲染 |

## 3. Monorepo 结构

```
zchat-mono/
├── pyproject.toml
├── packages/
│   ├── zchat-protocol/
│   │   └── src/zchat_protocol/
│   │       ├── datatypes/ (text, acp, migration, system_event, spawn_config)
│   │       ├── identity.py, message.py, annotation.py
│   │       ├── hook.py, index.py, timeline.py
│   │
│   ├── zchat-com/
│   │   └── src/zchat_com/
│   │       ├── core.py, message_router.py, network.py, room.py
│   │       ├── presence.py, identity.py, config.py
│   │       ├── store/ (outbox.py, relay.py, inbox.py)
│   │       ├── sync.py, stdio_bridge.py
│   │
│   ├── zchat-acp/
│   │   └── src/zchat_acp/
│   │       ├── server.py, interface.py, spawn.py, access.py, migrate.py
│   │       └── tmux/
│   │           ├── bridge.py, output_parser.py, access.py
│   │           └── agents/cc.py
│   │
│   ├── zchat-cli/
│   │   └── src/zchat_cli/
│   │       ├── __main__.py, api.py, preflight.py
│   │
│   └── zchat-tui/
│       └── src/zchat_tui/
│           ├── app.py
│           └── tui/ (sidebar, dashboard, chat, session_tab, command_bar, dialogs)
│
├── configs/templates/              ← 内置角色模板
│   ├── coder.toml
│   └── reviewer.toml
└── tests/
    ├── test_protocol/, test_com/, test_acp/
    ├── test_cli/, test_tui/, test_integration/
```

项目目录的 spawn 配置结构：

```
~/project/.zchat/
├── templates/         ← 角色模板（团队共享，git-tracked）
│   └── coder.toml
└── agents/            ← Agent 实例（git-tracked）
    └── ppt-maker.toml   (inherits = "coder")
```

`zchat template init` 从 configs/templates/ 复制到 .zchat/templates/。`zchat agent init --from coder` 从 .zchat/templates/coder.toml 派生到 .zchat/agents/。

## 4. 技术栈

asyncio · textual · libtmux · eclipse-zenoh · tomllib+tomli-w · pytest · uv workspace

## 5. 分发

```bash
uvx zchat           # 安装+启动
zchat afk <s>       # CLI 子命令
zchat preflight     # 前置检查
```

## 6. 开发阶段

详见 [dev-phases.md](./08-dev-phases.md)。

| Phase | 时间 | 并行 | E2E |
|---|---|---|---|
| 0: 骨架+Mock | 1周 | 1 agent | A-H mock |
| 1: 核心 | 2周 | 5 agents (α β γ δ ε) | A-E 真实 |
| 2: 迁移+离线 | 2周 | 4 agents (ζ η θ ι) | A-H 全真实 |
| 3: LAN+打磨 | 2周 | 2-3 agents | 跨机器 |
| 4: Mock消除 | 1周 | 1 agent | 确认无mock |

---

## 相关文档

- [架构概览](./01-overview.md) · [开发阶段](./08-dev-phases.md)
- [protocol](./02-protocol.md) · [com](./03-com.md) · [acp](./04-acp.md) · [cli](./05-cli.md) · [tui](./06-tui.md)
- [E2E](./07-e2e-scenarios.md) · [测试](./10-mvp-testcases.md)
