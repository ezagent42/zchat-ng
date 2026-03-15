# ZChat 设计文档 v0.0.6.3.1

## 全局概览

ZChat：LAN 多人 AI Agent 协作工具。4×2 原语体系，4 个核心包 + Extension 机制，Eclipse Zenoh P2P。当前仅支持 Claude Code 作为 Agent backend。

核心架构思想（**依赖反转**）：zchat-cli 是核心层——它定义所有操作的语义和 Backend 接口契约。zchat-protocol 是 cli 需求的形式化——将操作涉及的数据结构声明为类型。zchat-com 和 zchat-acp 是可替换的 Backend 实现——分别解决传输和适配问题，通过接口注入 cli。

```
    zchat-cli（核心层：操作定义 + Backend 接口）
        │
        │ 依赖类型定义
        ▼
    zchat-protocol（数据层：CLI 需求的形式化）
        ▲               ▲
        │ implements     │ implements
        │ ComBackend     │ AcpBackend
    zchat-com          zchat-acp
   （传输实现）       （适配实现）
```

**com/acp 不被 cli import——它们实现 cli 定义的接口，在启动时注入。**

### v0.0.6.3.1 主要变更（相对 v0.0.6.3）

- **依赖反转**：cli 从「粘合层」变为「核心层」。定义 ComBackend / AcpBackend Protocol，com/acp 实现并注入
- **文档重排序**：按依赖方向阅读——cli → protocol → com → acp

### v0.0.6.3 主要变更（相对 v0.0.5.2）

- **三分法**：Core / Extension / 推迟模块
- **Extension 机制**：宽容路由 + 热加载 + 回扫
- **CC ↔ ZChat 交互**：模型 1+2 共存，enriched message，AgentSkill
- **前端策略**：CLI + AgentSkill 优先
- **AFK 为默认**：attach/detach 替代 tmux 集成
- **Timeline → View**：为 Socialware 预留

## 文档索引（按依赖方向阅读）

| 文档 | 说明 |
|---|---|
| [架构概览](./01-overview.md) | **入口**——依赖反转 + 三分法 + CC ↔ ZChat 交互 |
| [zchat-cli](./02-cli.md) | **核心层**——操作定义 + ComBackend / AcpBackend 接口 |
| [zchat-protocol](./03-protocol.md) | **数据层**——8 个原语 schema + ExtensionManifest |
| [zchat-com](./04-com.md) | **传输实现**——implements ComBackend，Zenoh P2P |
| [zchat-acp](./05-acp.md) | **适配实现**——implements AcpBackend，CC Headless Adapter |
| [Extension 机制](./06-extension.md) | manifest + 宽容路由 + 热加载 + 回扫 |
| [zchat-tui](./07-tui.md) | TUI 前端 **（推迟实现）** |
| [E2E 场景](./08-e2e-scenarios.md) | 30 个 Core 场景 |
| [开发阶段](./09-dev-phases.md) | Phase 0-3，4 周 |
| [MVP 实现](./10-mvp-implementation.md) | Monorepo + 技术栈 |
| [测试用例](./11-mvp-testcases.md) | 30 E2E + 62 底层 |
| [AgentSkill](./zchat.md) | CC 的 zchat 操作指南 |

## 安装

```bash
uvx zchat
```

## 技术栈

Python 3.12+ · asyncio · Eclipse Zenoh · uv workspace
