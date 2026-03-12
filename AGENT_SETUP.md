# Agent Setup

Declarative config for Claude Code skills and tools.
Edit this file to add/remove dependencies. Changes are applied on next session start.

## Skills

<!-- Each line: <source> [-s <name>]... -->
<!-- Without -s flags, all skills from the source are installed -->
- obra/superpowers
- anthropics/claude-plugins-official -s skill-creator -s claude-md-improver -s claude-automation-recommender

## Tools

<!-- Each line: <command> | <install-hint> -->
- rtk | cargo install rtk-ai || see https://github.com/rtk-ai/rtk
- uv | curl -LsSf https://astral.sh/uv/install.sh | sh

## Project Skills

<!-- Project-local skills in .claude/skills/ are auto-discovered by Claude Code. -->
<!-- List them here for documentation only — no installation needed. -->
