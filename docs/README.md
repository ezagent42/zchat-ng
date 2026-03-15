# ZChat 文档

## 目录结构

```
docs/
├── design/        架构与设计文档（按版本归档）
├── guide/         用户指南（面向 zchat 使用者）
├── extension/     扩展开发指南（面向插件作者）
├── api/           Python API 参考（面向集成开发者）
└── adr/           Architecture Decision Records
```

---

## design/ — 设计文档

按版本归档的架构设计与演进记录。记录"为什么这样设计"。

**读者**：核心开发者、贡献者
**何时写**：设计阶段，每次架构变更产出新版本

| 版本 | 说明 | 状态 |
|---|---|---|
| [v0.0.6.3](./design/v0.0.6.3/README.md) | 依赖反转 + AFK Mode + Extension 机制 + CLI-First | **当前** |
| [v0.0.5.1](./design/v0.0.5.1/README.md) | 初版架构：4x2 原语体系 + 5 包设计 | 归档 |

---

## guide/ — 用户指南

面向终端用户的使用文档。记录"怎么用"。

**读者**：zchat 用户、CC Agent
**何时写**：Phase 1 后，CLI 可用时

规划内容：

| 文件 | 说明 |
|---|---|
| `getting-started.md` | 安装 + 首次运行 (`uvx zchat`)、引导流程、基本概念 |
| `cli-reference.md` | CLI 命令完整参考：send / watch / ask / spawn / rooms / members / doctor ... |
| `agent-skill.md` | CC Agent 如何与 zchat 交互（基于 design 中的 zchat.md 编写用户向版本） |
| `configuration.md` | `.zchat/` 目录结构、templates / agents TOML 配置、网络配置 |

---

## extension/ — 扩展开发指南

面向扩展（Extension）作者的开发文档。记录"怎么扩展"。

**读者**：扩展开发者
**何时写**：Phase 1 Extension 机制落地后

规划内容：

| 文件 | 说明 |
|---|---|
| `creating-extensions.md` | 从零创建一个 Extension：manifest 编写、hook 注册、content_type 定义 |
| `extension-api.md` | Extension 与 Core 的接口契约：可以做什么、不能做什么 |
| `builtin-extensions.md` | 内置扩展说明：ext-migrate（迁移）、ext-offline（离线同步） |

---

## api/ — Python API 参考

面向集成开发者的 API 文档。记录"接口是什么"。

**读者**：将 zchat 嵌入其他项目的开发者
**何时写**：Phase 1 接口稳定后

规划内容：

| 文件 | 说明 |
|---|---|
| `cli-api.md` | `ZChatCLI` 类公共方法、回调签名、使用示例 |
| `backend-interfaces.md` | `ComBackend` / `AcpBackend` Protocol 定义、实现要求 |
| `event-types.md` | `ZChatEvent` / Operation 类型系统、ContentType 完整列表 |

---

## adr/ — Architecture Decision Records

关键架构决策的记录。每个 ADR 记录一个决策的背景、方案对比和最终选择。

**读者**：未来的开发者（包括未来的自己）
**何时写**：每次做出影响架构的重大决策时

文件命名：`NNNN-简短标题.md`（如 `0001-dependency-inversion.md`）

格式模板：

```markdown
# NNNN. 标题

日期：YYYY-MM-DD
状态：accepted / superseded by NNNN

## 背景

做这个决策时面对的问题和约束。

## 方案

考虑过的方案及各自的 trade-off。

## 决策

最终选择了什么，为什么。

## 影响

这个决策对后续开发的影响。
```
