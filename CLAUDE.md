# Project

This project uses Agent Setup infrastructure for Claude Code.

## Skills & Tools

Skills and tools are declared in `AGENT_SETUP.md` and auto-installed on session start.
Edit `AGENT_SETUP.md` to add or remove dependencies.

## Conventions

- Python packages: use `uv`, not `pip`
- JavaScript packages: use `pnpm`, not `npm`/`npx`
- CLI commands are rewritten through RTK for token savings (if installed)
