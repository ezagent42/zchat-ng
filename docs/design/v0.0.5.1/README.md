# ZChat 设计文档 v0.0.5.1

## 全局概览

ZChat：LAN 多人 AI Agent 协作工具。4×2 原语体系，5 个包，Eclipse Zenoh P2P。当前仅支持 Claude Code 作为 Agent backend。

```
              zchat-protocol
            （原语定义层）
             /              \
        zchat-com          zchat-acp
      （人类侧通信）       （Agent 侧控制）
             \              /
          zchat-cli
        （统一命令接口）
               |
          zchat-tui
         （TUI 前端）
```

## 文档索引

| 文档 | 说明 |
|---|---|
| [架构概览](./01-overview.md) | **入口**——原语定义 + 包关系 |
| [zchat-protocol](./02-protocol.md) | 8 个原语 schema |
| [zchat-com](./03-com.md) | Identity, Room, Message, Timeline |
| [zchat-acp](./04-acp.md) | Hook, Access, tmux Backend (CC) |
| [zchat-cli](./05-cli.md) | 统一 API + Shell 命令 |
| [zchat-tui](./06-tui.md) | TUI 前端 |
| [E2E 场景](./07-e2e-scenarios.md) | 44 个用户故事 A-H |
| [开发阶段](./08-dev-phases.md) | Phase 0-4 + CC agent 并行 Track |
| [MVP 实现](./09-mvp-implementation.md) | Monorepo + 技术栈 |
| [测试用例](./10-mvp-testcases.md) | 44 E2E + 64 底层 |

## 安装

```bash
uvx zchat
```

## 技术栈

Python 3.12+ · asyncio · Eclipse Zenoh · Textual · libtmux · uv workspace
