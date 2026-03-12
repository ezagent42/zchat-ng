#!/usr/bin/env bash
# SessionStart hook — reads AGENT_SETUP.md, ensures skills and tools are installed.
# Idempotent: re-running on already-installed skills simply overwrites them.
# Uses hash-based change detection to skip install when AGENT_SETUP.md is unchanged.
set -euo pipefail

SETUP_FILE="${CLAUDE_PROJECT_DIR}/AGENT_SETUP.md"
HASH_FILE="${CLAUDE_PROJECT_DIR}/.agents/.last-setup-hash"
VERSION_FILE="${CLAUDE_PROJECT_DIR}/.claude/.template-version"
TEMPLATE_REPO="https://github.com/ezagent42/agent-setup.git"
WARNINGS=""

escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

# --- 1. Check AGENT_SETUP.md exists ---
if [ ! -f "$SETUP_FILE" ]; then
  cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "WARNING: AGENT_SETUP.md not found at project root. Skills and tools will not be managed. Create one from the template: https://github.com/ezagent42/agent-setup"
  }
}
EOF
  exit 0
fi

# --- 2. Parse ## Skills section ---
# Extract lines between "## Skills" and the next "##" heading, keep only "- " lines
SKILLS_SECTION=$(awk '/^## Skills$/{found=1;next} /^## /{found=0} found{print}' "$SETUP_FILE")
SKILL_LINES=$(echo "$SKILLS_SECTION" | grep '^- ' | sed 's/^- //' || true)

# --- 3. Parse ## Tools section ---
TOOLS_SECTION=$(awk '/^## Tools$/{found=1;next} /^## /{found=0} found{print}' "$SETUP_FILE")
TOOL_LINES=$(echo "$TOOLS_SECTION" | grep '^- ' | sed 's/^- //' || true)

# --- 4. Hash-based change detection ---
CURRENT_HASH=$(echo "$SKILL_LINES" | shasum -a 256 | cut -d' ' -f1)
STORED_HASH=""
if [ -f "$HASH_FILE" ]; then
  STORED_HASH=$(cat "$HASH_FILE")
fi

SETUP_CHANGED=false
if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
  SETUP_CHANGED=true
fi

# --- 5. Install skills if changed ---
INSTALL_ERRORS=""
if [ "$SETUP_CHANGED" = true ] && [ -n "$SKILL_LINES" ]; then
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    # Each line becomes: pnpm dlx skills add <args> --agent claude-code -y
    # Redirect all output away from stdout to avoid corrupting hook JSON
    if ! pnpm dlx skills add $line --agent claude-code -y </dev/null >/dev/null 2>&1; then
      INSTALL_ERRORS="${INSTALL_ERRORS}\nFailed to install: $line"
    fi
  done <<< "$SKILL_LINES"

  # --- 6. Update hash ---
  mkdir -p "$(dirname "$HASH_FILE")"
  echo "$CURRENT_HASH" > "$HASH_FILE"
fi

# --- 7. Check tools ---
if [ -n "$TOOL_LINES" ]; then
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    TOOL_CMD=$(echo "$line" | cut -d'|' -f1 | xargs)
    TOOL_HINT=$(echo "$line" | cut -d'|' -f2- | xargs)
    if ! command -v "$TOOL_CMD" &>/dev/null; then
      WARNINGS="${WARNINGS}\nMissing tool: ${TOOL_CMD} — Install: ${TOOL_HINT}"
    fi
  done <<< "$TOOL_LINES"
fi

# --- 8. Check template version (non-blocking) ---
UPDATE_NOTICE=""
if [ -f "$VERSION_FILE" ]; then
  LOCAL_SHA=$(cat "$VERSION_FILE")
  # git ls-remote is fast (~200ms), only fetches ref metadata
  REMOTE_SHA=$(git ls-remote "$TEMPLATE_REPO" refs/heads/main 2>/dev/null | cut -f1 || true)
  if [ -n "$REMOTE_SHA" ] && [ "$REMOTE_SHA" != "$LOCAL_SHA" ]; then
    UPDATE_NOTICE="agent-setup template update available (${REMOTE_SHA:0:7}). Run: ./update-from-template.sh"
  fi
fi

# --- 9. Output JSON ---
if [ "$SETUP_CHANGED" = true ] && [ -n "$SKILL_LINES" ]; then
  MSG="Agent Setup updated. Please restart Claude Code to load new skills."
  if [ -n "$INSTALL_ERRORS" ]; then
    MSG="${MSG}\\nInstall errors:${INSTALL_ERRORS}"
  fi
  if [ -n "$WARNINGS" ]; then
    MSG="${MSG}\\n${WARNINGS}"
  fi
else
  MSG="All Agent Setup ✓"
  if [ -n "$WARNINGS" ]; then
    MSG="${MSG}\\n${WARNINGS}"
  fi
fi

if [ -n "$UPDATE_NOTICE" ]; then
  MSG="${MSG}\\n${UPDATE_NOTICE}"
fi

# Escape for JSON
MSG=$(escape_for_json "$MSG")

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "${MSG}"
  }
}
EOF

exit 0
