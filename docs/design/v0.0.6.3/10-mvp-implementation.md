# MVP 实现设计 v0.0.6.3

---

## 1. 包依赖（依赖反转）

```
zchat-cli:       → zchat-protocol        ← 核心层，定义操作 + Backend 接口
zchat-protocol:  无依赖                    ← 数据层，类型定义
zchat-com:       → zchat-protocol        ← 传输实现，implements ComBackend
zchat-acp:       → zchat-protocol        ← 适配实现，implements AcpBackend
zchat-ext-*:     → zchat-protocol        ← Extension 独立包
zchat-tui:       → zchat-cli             ← 推迟实现
```

**cli 不 import com/acp。com/acp 实现 cli 定义的 Protocol 接口，在 `__main__.py` 中注入。**

当前仅支持 Claude Code (AFK headless mode)。

## 2. 原语 → 模块映射

| 原语 | 定义在 (protocol) | 实现在 |
|---|---|---|
| ContentType | `datatypes/*.py` | 所有包 |
| Hook | `hook.py` | acp: `server.py`(调度), `spawn.py`(注册), extension(动态注册) |
| Annotation | `annotation.py` | com: `event_router.py`(路由时附加 per-recipient) |
| Index | `index.py` | com: `event_router.py`(Room subscription) |
| Identity | `identity.py` | com: `identity.py`, `network.py` |
| Room | — | com: `room.py` (= Matrix Room) |
| Message | `message.py` + `zchat_event.py` | com: `event_router.py`, acp: 构造 ZChat Operation |
| View | `view.py` | com: `event_store.py`(查询), cli: `watch`(渲染) |
| ComBackend | `backends.py` (in cli) | com: `ZenohComBackend` |
| AcpBackend | `backends.py` (in cli) | acp: `HeadlessAcpBackend` |
| ExtensionManifest | `extension_manifest.py` | cli: `ext_registry.py`(解析+注册) |

## 3. Monorepo 结构

```
zchat-mono/
├── pyproject.toml
├── packages/
│   ├── zchat-protocol/
│   │   └── src/zchat_protocol/
│   │       ├── content_types/ (text, acp, system-event, spawn-config)
│   │       ├── identity.py, message.py, zchat_event.py, annotation.py
│   │       ├── hook.py, index.py, view.py
│   │       ├── operation_types.py
│   │       └── extension_manifest.py             ← new: Extension manifest schema
│   │
│   ├── zchat-com/
│   │   └── src/zchat_com/
│   │       ├── core.py, event_router.py, network.py, room.py
│   │       ├── presence.py, identity.py, config.py
│   │       ├── store/event_store.py              ← JSONL / SQLite
│   │       └── sync.py                           ← 简单 queryable backfill
│   │
│   ├── zchat-acp/
│   │   └── src/zchat_acp/
│   │       ├── server.py, interface.py, spawn.py, access.py
│   │       ├── pool.py, workspace.py
│   │       ├── headless/                         ← AFK Mode (默认)
│   │       │   ├── process.py, translator.py
│   │       │   ├── enriched_message.py           ← new: [zchat] 格式构造
│   │       │   └── ask_bridge.py
│   │       └── tmux/                             ← 推迟实现
│   │           ├── bridge.py, output_parser.py, access.py
│   │           └── agents/cc.py
│   │
│   ├── zchat-cli/                                ← 核心层
│   │   └── src/zchat_cli/
│   │       ├── __main__.py                        ← 组装 Backend + 启动
│   │       ├── api.py                             ← 操作语义实现
│   │       ├── backends.py                        ← ComBackend / AcpBackend Protocol 定义
│   │       ├── preflight.py
│   │       └── ext_registry.py                    ← Extension 热加载 + 回扫
│   │
│   └── zchat-tui/                                ← 推迟实现
│       └── src/zchat_tui/
│           ├── app.py
│           └── tui/ (sidebar, dashboard, chat, session_tab, command_bar, dialogs)
│
├── configs/templates/              ← 内置角色模板
│   ├── coder.toml
│   └── reviewer.toml
├── zchat.md                        ← new: AgentSkill
└── tests/
    ├── test_protocol/, test_com/, test_acp/
    ├── test_cli/, test_extension/
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

asyncio · eclipse-zenoh · tomllib+tomli-w · pytest · uv workspace

> **v0.0.6 变更**：移除 textual（TUI 推迟）、libtmux（Direct Mode 推迟）。

## 5. 分发

```bash
uvx zchat           # 安装+启动长驻进程
zchat watch         # 实时查看
zchat send ...      # 发消息
zchat preflight     # 前置检查
```

## 6. 开发阶段

详见 [dev-phases.md](./09-dev-phases.md)。

| Phase | 时间 | 并行 | E2E |
|---|---|---|---|
| 0: 骨架+Mock | 1周 | 1 agent | 全 CLI mock |
| 1: 核心 | 2周 | 3 agents (α β γ) | A-E + G-alt + H 真实 |
| 2: LAN+打磨 | 1周 | 1-2 agents | 跨机器 |
| 3: Mock消除 | 2-3天 | 1 agent | 确认无mock |

---

## 相关文档

- [架构概览](./01-overview.md) · [开发阶段](./09-dev-phases.md)
- [protocol](./03-protocol.md) · [com](./04-com.md) · [acp](./05-acp.md) · [cli](./02-cli.md) · [tui](./07-tui.md)
- [E2E](./08-e2e-scenarios.md) · [测试](./11-mvp-testcases.md) · [Extension 机制](./06-extension.md)
