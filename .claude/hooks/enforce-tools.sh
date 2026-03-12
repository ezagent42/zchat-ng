#!/usr/bin/env bash
# enforce-tools.sh — Block forbidden package managers, suggest alternatives.
# Configured as a PreToolUse hook for the Bash tool.

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

[ -z "$COMMAND" ] && exit 0

# --- Python: pip → uv ---
# Match pip/pip3 only at command position (start of line or after shell operator)
if echo "$COMMAND" | grep -qE '(^|[;&|])[[:space:]]*(pip|pip3)([[:space:]]|$)'; then
  cat >&2 <<'MSG'
BLOCKED: pip is not allowed. Use uv instead.

  pip install foo       → uv pip install foo
  pip uninstall foo     → uv pip uninstall foo
  pip freeze            → uv pip freeze
  pip install -r req.txt → uv pip install -r req.txt

See CONTRIBUTING.md for details.
MSG
  exit 2
fi

if echo "$COMMAND" | grep -qE '(^|[;&|])[[:space:]]*(python|python3)[[:space:]]+-m[[:space:]]+pip([[:space:]]|$)'; then
  echo "BLOCKED: python -m pip is not allowed. Use 'uv pip' instead. See CONTRIBUTING.md." >&2
  exit 2
fi

# --- Python: python/python3 → uv run ---
# Block bare python/python3 invocations (allow inside uv run / uvx / curl pipes)
if echo "$COMMAND" | grep -qE '(^|[;&|])[[:space:]]*(python|python3)([[:space:]]|$)' \
   && ! echo "$COMMAND" | grep -qE '(uv run|uvx)'; then
  cat >&2 <<'MSG'
BLOCKED: Direct python/python3 is not allowed. Use uv run instead.

  python script.py        → uv run python script.py
  python -m pytest        → uv run pytest
  python3 -m pytest       → uv run pytest
  python3 -c "..."        → uv run python3 -c "..."

See CONTRIBUTING.md for details.
MSG
  exit 2
fi

# --- Python: .venv/bin/* → uv run ---
# Block direct .venv/bin/ invocations (should use uv run instead)
if echo "$COMMAND" | grep -qE '(^|[;&|])[[:space:]]*\.?/?\.venv/bin/'; then
  cat >&2 <<'MSG'
BLOCKED: Direct .venv/bin/ invocations are not allowed. Use uv run instead.

  .venv/bin/pytest        → uv run pytest
  .venv/bin/zchat         → uv run zchat
  .venv/bin/python        → uv run python

See CONTRIBUTING.md for details.
MSG
  exit 2
fi

# --- JavaScript: npm/npx → pnpm ---
if echo "$COMMAND" | grep -qE '(^|[;&|])[[:space:]]*npm([[:space:]]|$)'; then
  cat >&2 <<'MSG'
BLOCKED: npm is not allowed. Use pnpm instead.

  npm install           → pnpm install
  npm install foo       → pnpm add foo
  npm run dev           → pnpm run dev
  npm init              → pnpm create
  npm exec foo          → pnpm exec foo
  npm ci                → pnpm install --frozen-lockfile

See CONTRIBUTING.md for details.
MSG
  exit 2
fi

if echo "$COMMAND" | grep -qE '(^|[;&|])[[:space:]]*npx([[:space:]]|$)'; then
  echo "BLOCKED: npx is not allowed. Use 'pnpm dlx' (one-off) or 'pnpm exec' (local) instead. See CONTRIBUTING.md." >&2
  exit 2
fi

exit 0
