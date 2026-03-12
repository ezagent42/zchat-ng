# Agent Setup

可复用的 Claude Code 基础设施 — hooks、skills、commands 和 agents — 通过 `AGENT_SETUP.md` 声明式管理。

## 包含内容

- **SessionStart hooks**: 从 `AGENT_SETUP.md` 自动安装 skills、注入 superpowers 上下文、学习模式
- **PreToolUse hooks**: 强制使用 `uv`/`pnpm` 替代 `pip`/`npm`、RTK 命令重写以节省 token
- **Commands**: `/brainstorm`、`/write-plan`、`/execute-plan`、`/commit`、`/commit-push-pr`、`/clean_gone`、`/revise-claude-md`
- **Agents**: `code-reviewer`
- **启动器**: `claude.sh` — 带 tmux 封装的 Claude Code，支持用户本地配置覆盖

## 快速开始

### 新项目

```bash
gh repo create my-project --template ezagent42/agent-setup --clone
cd my-project
./claude.sh
```

### 已有项目（一行搞定）

在项目目录中启动 Claude Code，将以下 prompt 粘贴到 Claude 中：

~~~
Clone https://github.com/ezagent42/agent-setup to a temp directory. Copy its
update-from-template.sh to this project root, then run ./update-from-template.sh --init
to bootstrap Claude Code infrastructure. Follow the script's prompts.
~~~

### 手动安装

```bash
# 在你的项目目录中
curl -fsSL https://raw.githubusercontent.com/ezagent42/agent-setup/main/update-from-template.sh -o update-from-template.sh
chmod +x update-from-template.sh
./update-from-template.sh --init
```

## 更新

从模板拉取最新的基础设施文件：

```bash
./update-from-template.sh
```

基础设施文件（hooks、启动器、RTK 文档）始终会被覆盖。
配置文件（commands、agents）仅在你未修改的情况下才会更新。

## 自定义

### `AGENT_SETUP.md`

编辑此文件来声明 skills 和 tools。更改会在下次 Claude Code 会话启动时生效。

```markdown
## Skills
- obra/superpowers
- anthropics/claude-plugins-official -s skill-creator -s claude-md-improver

## Tools
- rtk | cargo install rtk-ai
- uv | curl -LsSf https://astral.sh/uv/install.sh | sh
```

### `claude.local.sh`

用户特定配置（代理、API 密钥等）放在 `claude.local.sh` 中（已 gitignore）：

```bash
export ALL_PROXY=http://127.0.0.1:7897
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
```

### 项目特定 hooks

在 `.claude/settings.json` 中添加你自己的 hooks。更新脚本会保留所有项目特定的条目（Stop hooks、自定义 PreToolUse hooks 等）。

## 工作原理

1. **SessionStart**: `agent-setup.sh` 读取 `AGENT_SETUP.md`，对 Skills 部分计算哈希
2. **哈希匹配** → 跳过安装（快速，无需网络）。**哈希不匹配** → 对每个 source 执行 `pnpm dlx skills add`
3. **工具检查**: 验证所需的 CLI 工具是否已安装，缺失时显示安装提示
4. **Skills** 安装到 `.agents/`（已 gitignore，每次会话启动时恢复）

## 模板结构

```
agent-setup/
├── AGENT_SETUP.md                  # 声明 skills + tools
├── CLAUDE.md                       # 最小化 CLAUDE.md（项目可覆盖）
├── claude.sh                       # tmux 封装的 Claude Code 启动器
├── update-from-template.sh         # 从模板初始化/更新
├── .claude/
│   ├── settings.json               # Hooks 配置
│   ├── hooks/
│   │   ├── agent-setup.sh          # 核心：解析 AGENT_SETUP.md，安装 skills，检查 tools
│   │   ├── inject-superpowers.sh   # 注入 using-superpowers 上下文
│   │   ├── learning-output-style.sh # 学习模式上下文
│   │   ├── enforce-tools.sh        # 阻止 pip/npm → uv/pnpm
│   │   └── rtk-rewrite.sh         # RTK 命令重写（PreToolUse）
│   ├── commands/                   # 7 个命令文件
│   ├── agents/
│   │   └── code-reviewer.md
│   └── RTK.md
├── .gitignore
└── README.md
```

## 依赖

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- [pnpm](https://pnpm.io/)（用于 `pnpm dlx skills`）
- [gh](https://cli.github.com/)（用于模板创建和手动安装）
