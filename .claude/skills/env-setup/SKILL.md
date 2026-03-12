---
name: env-setup
description: Guide for adding and configuring Claude Code development infrastructure — skills, hooks, subagents, MCP servers, commands, and environment settings. Use this skill whenever the user wants to add a new skill, create a hook, set up an MCP server, add a subagent definition, create a slash command, configure claude.local.sh, or asks "how do I add X to my Claude Code setup". Also trigger when someone mentions AGENT_SETUP.md, .mcp.env, claude.local.sh, or asks about the agent-setup template structure.
---

# Environment Setup Guide

This skill helps you configure Claude Code infrastructure in projects that use the `agent-setup` template. Each section covers one type of configuration with the exact files, formats, and steps needed.

## Quick Reference

| What to add | Where it goes | How to apply |
|---|---|---|
| Skill (external) | `AGENT_SETUP.md` → `## Skills` | Next session start (auto-installed) |
| Skill (project-local) | `.claude/skills/<name>/SKILL.md` | Immediate (Claude discovers it) |
| Hook | `.claude/settings.json` → `hooks` | Next session start |
| Subagent | `.claude/agents/<name>.md` | Immediate (Claude discovers it) |
| MCP server | `.claude/mcp.json` | Next session start (with `--mcp-config`) |
| MCP secrets | `.mcp.env` | Next `./claude.sh` launch |
| Slash command | `.claude/commands/<name>.md` | Immediate (Claude discovers it) |
| Environment vars | `claude.local.sh` | Next `./claude.sh` launch |

---

## 1. Adding Skills

### External skills (from GitHub)

Edit `AGENT_SETUP.md` and add entries under `## Skills`:

```markdown
## Skills
- owner/repo
- owner/repo -s specific-skill-1 -s specific-skill-2
```

Format: each line is a `pnpm dlx skills add` argument. Use `-s <name>` to select specific skills from a repo that contains multiple.

**Example — add the `skill-creator` skill:**
```markdown
## Skills
- obra/superpowers
- anthropics/claude-plugins-official -s skill-creator
```

Changes take effect on next Claude Code session start. The `agent-setup.sh` hook detects changes by comparing a SHA-256 hash of the Skills section.

### Project-local skills

Create a skill directory directly:

```
.claude/skills/my-skill/
└── SKILL.md
```

SKILL.md format:
```markdown
---
name: my-skill
description: When to trigger this skill and what it does. Be specific about trigger conditions.
---

# My Skill

Instructions for Claude when this skill is invoked...
```

Project-local skills are discovered immediately — no session restart needed.

**Bundled resources** (optional): add `scripts/`, `references/`, or `assets/` subdirectories for supporting files that the skill can reference.

---

## 2. Adding Hooks

Hooks are shell scripts triggered by Claude Code events. Edit `.claude/settings.json` to register them.

### Hook types

| Event | When it fires | Common use |
|---|---|---|
| `SessionStart` | Session begins | Inject context, check tools, install dependencies |
| `PreToolUse` | Before a tool runs | Rewrite commands, block dangerous operations, enforce policies |
| `PostToolUse` | After a tool runs | Validate output, log actions |
| `Stop` | Session ends | Cleanup, stop background processes |

### Creating a hook

1. Write the hook script in `.claude/hooks/`:

```bash
#!/usr/bin/env bash
# .claude/hooks/my-hook.sh

# SessionStart hooks output JSON with additionalContext:
# (only for SessionStart — other hooks have different output formats)

MESSAGE="Context to inject into the session"
jq -n --arg msg "$MESSAGE" '{
  "hookSpecificOutput": {
    "additionalContext": $msg
  }
}'
```

2. Make it executable: `chmod +x .claude/hooks/my-hook.sh`

3. Register in `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [{
          "type": "command",
          "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/my-hook.sh"
        }]
      }
    ]
  }
}
```

### PreToolUse hooks

PreToolUse hooks receive tool input on stdin as JSON and can:
- **Allow**: exit 0 with no output
- **Block**: output JSON with `"permissionDecision": "deny"`
- **Rewrite**: output JSON with `"permissionDecision": "allow"` and `"updatedInput"`

```bash
#!/usr/bin/env bash
# PreToolUse hook that blocks a specific pattern
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if echo "$CMD" | grep -q "rm -rf /"; then
  jq -n '{
    "hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "deny",
      "permissionDecisionReason": "Blocked dangerous command"
    }
  }'
else
  exit 0
fi
```

Register with a matcher to scope which tools trigger it:
```json
{
  "matcher": "Bash",
  "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/my-hook.sh" }]
}
```

---

## 3. Adding Subagents

Subagent definitions go in `.claude/agents/<name>.md`. These define specialized agent personas that Claude can spawn via the Agent tool.

```markdown
---
name: my-agent
description: What this agent does and when to use it
tools: [Bash, Read, Write, Edit, Grep, Glob]
---

# My Agent

You are a specialized agent for [purpose].

## Instructions
...
```

Key fields in frontmatter:
- `name`: Agent identifier
- `description`: When Claude should spawn this agent
- `tools`: Which tools the agent can use (subset of available tools)
- `model` (optional): Override model (e.g., `sonnet` for faster/cheaper tasks)

Subagents are discovered immediately — no restart needed. They appear as `subagent_type` options in the Agent tool.

**Important:** `.claude/agents/` (subagent definitions, committed to git) is completely separate from `.agents/` (skills CLI runtime, gitignored). They serve different purposes and never conflict.

---

## 4. Adding MCP Servers

MCP (Model Context Protocol) servers extend Claude's capabilities with external tools.

### Server configuration

Edit `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@package/mcp-server"],
      "env": {
        "API_KEY": ""
      }
    }
  }
}
```

### Secrets management

API keys and tokens go in `.mcp.env` (gitignored, loaded by `claude.sh`):

```bash
# .mcp.env
SERVER_NAME_API_KEY=your-key-here
ANOTHER_SECRET=another-value
```

Reference these in `mcp.json` via environment variables. The `claude.sh` launcher auto-loads `.mcp.env` with `set -a` (auto-export) before starting Claude.

### Common MCP servers

| Server | Package | Purpose |
|---|---|---|
| Context7 | `@upstash/context7-mcp` | Library documentation lookup |
| GitHub | `@modelcontextprotocol/server-github` | GitHub API access |
| Filesystem | `@modelcontextprotocol/server-filesystem` | Extended file operations |

MCP config takes effect on next session start (passed via `--mcp-config`).

---

## 5. Adding Slash Commands

Slash commands are markdown files in `.claude/commands/`. Users invoke them with `/<name>`.

Create `.claude/commands/my-command.md`:

```markdown
---
description: What this command does (shown in command list)
---

Instructions for Claude when this command is invoked.

$ARGUMENTS will be replaced with whatever the user types after the command name.
```

- File name (minus `.md`) becomes the command name: `my-command.md` → `/my-command`
- `$ARGUMENTS` is a special placeholder for user input after the command
- Commands are discovered immediately

---

## 6. Environment Configuration

### `claude.local.sh` (user-specific, gitignored)

For proxy settings, API keys, and other machine-specific configuration:

```bash
# claude.local.sh
export ALL_PROXY=http://127.0.0.1:7897
export ANTHROPIC_API_KEY=sk-ant-...
export CLAUDE_CODE_MAX_TOKENS=200000
```

Sourced by `claude.sh` on every launch. Never commit this file.

### `.mcp.env` (MCP secrets, gitignored)

Specifically for MCP server secrets, auto-exported:

```bash
# .mcp.env
CONTEXT7_API_KEY=your-key
GITHUB_TOKEN=ghp_...
```

### `AGENT_SETUP.md` → `## Tools`

Declare required CLI tools with install instructions:

```markdown
## Tools
- rtk | cargo install rtk-ai || see https://github.com/rtk-ai/rtk
- uv | curl -LsSf https://astral.sh/uv/install.sh | sh
- jq | brew install jq
```

Format: `tool-name | install-command`. The `agent-setup.sh` hook checks these on session start and warns if missing.

---

## 7. Template Update Flow

After modifying template files in `agent-setup`, propagate to consuming projects:

```bash
# In the consuming project
./update-from-template.sh
```

- **Infrastructure files** (hooks, claude.sh, RTK.md): always overwritten
- **Config files** (commands, agents): only updated if not locally modified (checksum-based detection)
- **User files** (AGENT_SETUP.md, mcp.json, settings.json): never overwritten

To add new files to the template update flow, edit `update-from-template.sh` and add them to the appropriate category (INFRA_FILES for always-overwrite, or the config loop for checksum-guarded).
