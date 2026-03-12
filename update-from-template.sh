#!/usr/bin/env bash
# update-from-template.sh — Bootstrap or update project from ezagent42/agent-setup template.
#
# Usage:
#   ./update-from-template.sh --init   # First-time setup (handles legacy cleanup)
#   ./update-from-template.sh          # Update infrastructure from latest template
set -euo pipefail

TEMPLATE_REPO="https://github.com/ezagent42/agent-setup.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
CHECKSUMS_FILE="$PROJECT_DIR/.claude/.template-checksums"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[agent-setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[agent-setup]${NC} $*"; }
error() { echo -e "${RED}[agent-setup]${NC} $*" >&2; }

# --- Clone template to temp dir ---
clone_template() {
  local tmpdir
  tmpdir=$(mktemp -d)
  info "Cloning template from $TEMPLATE_REPO..." >&2
  git clone --depth 1 "$TEMPLATE_REPO" "$tmpdir" 2>/dev/null
  echo "$tmpdir"
}

# --- Save template version (commit SHA) ---
save_template_version() {
  local template_dir="$1"
  local version_file="$PROJECT_DIR/.claude/.template-version"
  local sha
  sha=$(git -C "$template_dir" rev-parse HEAD 2>/dev/null || true)
  if [ -n "$sha" ]; then
    echo "$sha" > "$version_file"
    info "  Saved template version: ${sha:0:7}"
  fi
}

# --- Compute checksums of template files ---
compute_checksums() {
  local template_dir="$1"
  local checksum_file="$2"
  : > "$checksum_file"
  # Infrastructure files (glob must expand in template_dir)
  for f in "$template_dir"/claude.sh "$template_dir"/update-from-template.sh "$template_dir"/.claude/hooks/*.sh "$template_dir"/.claude/RTK.md; do
    if [ -f "$f" ]; then
      local relpath="${f#$template_dir/}"
      echo "$(shasum -a 256 "$f" | cut -d' ' -f1)  $relpath" >> "$checksum_file"
    fi
  done
  # Config files
  for f in "$template_dir"/.claude/commands/*.md "$template_dir"/.claude/agents/*.md; do
    if [ -f "$f" ]; then
      local relpath="${f#$template_dir/}"
      echo "$(shasum -a 256 "$f" | cut -d' ' -f1)  $relpath" >> "$checksum_file"
    fi
  done
  # Bundled skills
  for f in "$template_dir"/.claude/skills/*/SKILL.md; do
    if [ -f "$f" ]; then
      local relpath="${f#$template_dir/}"
      echo "$(shasum -a 256 "$f" | cut -d' ' -f1)  $relpath" >> "$checksum_file"
    fi
  done
}

# --- Get stored checksum for a file ---
get_stored_checksum() {
  local file="$1"
  if [ -f "$CHECKSUMS_FILE" ]; then
    grep "  ${file}$" "$CHECKSUMS_FILE" | cut -d' ' -f1 || true
  fi
}

# --- Copy file, creating parent dirs ---
copy_file() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
}

# ============================================
# --init mode: bootstrap from template
# ============================================
do_init() {
  echo ""
  warn "This will:"
  echo "  - Remove git submodules (.claude/vendor/)"
  echo "  - Remove vendored skill symlinks from .claude/skills/"
  echo "  - Remove legacy hooks (check-plugins.sh, skills-session-start.sh, etc.)"
  echo "  - Remove .claude/zchat-mode.json"
  echo "  - Remove .agents/ directory"
  echo "  - Copy template infrastructure files"
  echo "  - Install skills from AGENT_SETUP.md"
  echo ""
  read -p "Continue? [y/N] " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    info "Aborted."
    exit 0
  fi

  # Safety net
  info "Creating git stash as safety net..."
  git stash push -m "agent-setup --init backup $(date +%Y%m%d-%H%M%S)" 2>/dev/null || true

  # Clone template
  TEMPLATE_DIR=$(clone_template)
  trap "rm -rf '$TEMPLATE_DIR'" EXIT

  # --- 1. Clean up legacy content ---
  info "Cleaning up legacy content..."

  # 1a. Deinit and remove git submodules
  if [ -f "$PROJECT_DIR/.gitmodules" ]; then
    info "  Removing git submodules..."
    (cd "$PROJECT_DIR" && git submodule deinit --all --force 2>/dev/null || true)
    rm -rf "$PROJECT_DIR/.claude/vendor/"
    rm -f "$PROJECT_DIR/.gitmodules"
    # Clean .git/modules
    rm -rf "$PROJECT_DIR/.git/modules/.claude/" 2>/dev/null || true
  fi

  # 1b. Remove ALL symlinks from .claude/skills/
  if [ -d "$PROJECT_DIR/.claude/skills/" ]; then
    info "  Removing symlinks from .claude/skills/..."
    find "$PROJECT_DIR/.claude/skills/" -maxdepth 1 -type l -delete
  fi

  # 1c. Remove known vendored skill directories
  VENDORED_SKILLS=(
    brainstorming dispatching-parallel-agents executing-plans
    finishing-a-development-branch receiving-code-review
    requesting-code-review subagent-driven-development
    systematic-debugging test-driven-development using-git-worktrees
    using-superpowers verification-before-completion writing-plans
    writing-skills skill-creator
  )
  for skill in "${VENDORED_SKILLS[@]}"; do
    if [ -d "$PROJECT_DIR/.claude/skills/$skill" ]; then
      info "  Removing vendored skill: $skill"
      rm -rf "$PROJECT_DIR/.claude/skills/$skill"
    fi
  done

  # 1d. Remove legacy hooks
  LEGACY_HOOKS=(
    superpowers-session-start.sh skills-session-start.sh
    check-plugins.sh check-rtk.sh
    learning-output-style-session-start.sh
  )
  for hook in "${LEGACY_HOOKS[@]}"; do
    if [ -f "$PROJECT_DIR/.claude/hooks/$hook" ] || [ -L "$PROJECT_DIR/.claude/hooks/$hook" ]; then
      info "  Removing legacy hook: $hook"
      rm -f "$PROJECT_DIR/.claude/hooks/$hook"
    fi
  done

  # 1e. Remove zchat-mode.json
  if [ -f "$PROJECT_DIR/.claude/zchat-mode.json" ]; then
    info "  Removing .claude/zchat-mode.json"
    rm -f "$PROJECT_DIR/.claude/zchat-mode.json"
  fi

  # 1f. Remove enabledPlugins from settings.json
  if [ -f "$PROJECT_DIR/.claude/settings.json" ] && command -v jq &>/dev/null; then
    if jq -e '.enabledPlugins' "$PROJECT_DIR/.claude/settings.json" &>/dev/null; then
      info "  Removing enabledPlugins from settings.json"
      jq 'del(.enabledPlugins)' "$PROJECT_DIR/.claude/settings.json" > "$PROJECT_DIR/.claude/settings.json.tmp"
      mv "$PROJECT_DIR/.claude/settings.json.tmp" "$PROJECT_DIR/.claude/settings.json"
    fi
  fi

  # 1g. Remove .agents/ directory
  if [ -d "$PROJECT_DIR/.agents" ]; then
    info "  Removing .agents/ directory (will be recreated by skills CLI)"
    rm -rf "$PROJECT_DIR/.agents"
  fi

  # --- 2. Copy template files ---
  info "Copying template files..."

  # AGENT_SETUP.md → only if not exists
  if [ ! -f "$PROJECT_DIR/AGENT_SETUP.md" ]; then
    copy_file "$TEMPLATE_DIR/AGENT_SETUP.md" "$PROJECT_DIR/AGENT_SETUP.md"
    info "  Created AGENT_SETUP.md"
  else
    info "  AGENT_SETUP.md already exists, skipping"
  fi

  # claude.sh → always overwrite
  copy_file "$TEMPLATE_DIR/claude.sh" "$PROJECT_DIR/claude.sh"
  chmod +x "$PROJECT_DIR/claude.sh"
  info "  Updated claude.sh"

  # update-from-template.sh → always overwrite (self-update)
  copy_file "$TEMPLATE_DIR/update-from-template.sh" "$PROJECT_DIR/update-from-template.sh"
  chmod +x "$PROJECT_DIR/update-from-template.sh"
  info "  Updated update-from-template.sh"

  # .claude/hooks/* → always overwrite
  for f in "$TEMPLATE_DIR"/.claude/hooks/*.sh; do
    [ -f "$f" ] || continue
    fname=$(basename "$f")
    copy_file "$f" "$PROJECT_DIR/.claude/hooks/$fname"
    chmod +x "$PROJECT_DIR/.claude/hooks/$fname"
    info "  Updated hook: $fname"
  done

  # .claude/commands/* → only if not exists
  for f in "$TEMPLATE_DIR"/.claude/commands/*.md; do
    [ -f "$f" ] || continue
    fname=$(basename "$f")
    if [ ! -f "$PROJECT_DIR/.claude/commands/$fname" ]; then
      copy_file "$f" "$PROJECT_DIR/.claude/commands/$fname"
      info "  Created command: $fname"
    else
      info "  Command $fname already exists, skipping"
    fi
  done

  # .claude/agents/code-reviewer.md → only if not exists
  if [ ! -f "$PROJECT_DIR/.claude/agents/code-reviewer.md" ]; then
    copy_file "$TEMPLATE_DIR/.claude/agents/code-reviewer.md" "$PROJECT_DIR/.claude/agents/code-reviewer.md"
    info "  Created agent: code-reviewer.md"
  fi

  # .claude/RTK.md → always overwrite
  copy_file "$TEMPLATE_DIR/.claude/RTK.md" "$PROJECT_DIR/.claude/RTK.md"
  info "  Updated RTK.md"

  # .claude/mcp.json → only if not exists (users add their own MCP servers)
  if [ ! -f "$PROJECT_DIR/.claude/mcp.json" ]; then
    copy_file "$TEMPLATE_DIR/.claude/mcp.json" "$PROJECT_DIR/.claude/mcp.json"
    info "  Created mcp.json"
  else
    info "  mcp.json already exists, skipping"
  fi

  # .mcp.env.example → always overwrite (template may add new keys)
  if [ -f "$TEMPLATE_DIR/.mcp.env.example" ]; then
    copy_file "$TEMPLATE_DIR/.mcp.env.example" "$PROJECT_DIR/.mcp.env.example"
    info "  Updated .mcp.env.example"
  fi

  # .claude/skills/* → bundled skills, only if not exists (skip symlinks)
  if [ -d "$TEMPLATE_DIR/.claude/skills" ]; then
    for skill_dir in "$TEMPLATE_DIR"/.claude/skills/*/; do
      [ -d "$skill_dir" ] || continue
      skill_name=$(basename "$skill_dir")
      project_skill="$PROJECT_DIR/.claude/skills/$skill_name"
      if [ -L "$project_skill" ]; then
        info "  Skill $skill_name is a symlink (managed by skills CLI), skipping"
      elif [ ! -d "$project_skill" ]; then
        mkdir -p "$project_skill"
        cp -r "$skill_dir"* "$project_skill/"
        info "  Created skill: $skill_name"
      else
        info "  Skill $skill_name already exists, skipping"
      fi
    done
  fi

  # --- 3. Merge settings.json ---
  info "Merging settings.json..."
  if command -v jq &>/dev/null; then
    TEMPLATE_SETTINGS="$TEMPLATE_DIR/.claude/settings.json"
    PROJECT_SETTINGS="$PROJECT_DIR/.claude/settings.json"

    if [ -f "$PROJECT_SETTINGS" ]; then
      # Build merged settings: project base + template hooks
      MERGED=$(jq --slurpfile tmpl "$TEMPLATE_SETTINGS" '
        # Start with project settings
        . as $project |

        # Remove legacy hooks from all hook arrays
        (.hooks // {}) | to_entries | map(
          .value |= map(
            select(
              (.hooks // []) | all(
                .command | test("check-plugins\\.sh|superpowers-session-start\\.sh|skills-session-start\\.sh|check-rtk\\.sh|learning-output-style-session-start\\.sh") | not
              )
            )
          )
        ) | from_entries as $cleaned_hooks |

        # Template hooks
        ($tmpl[0].hooks // {}) as $template_hooks |

        # Merge: keep existing cleaned hooks, add template hooks for each event
        ([$cleaned_hooks | to_entries[], $template_hooks | to_entries[]] | group_by(.key) | map(
          {
            key: .[0].key,
            value: (
              [.[].value[]] | unique_by(.hooks[0].command)
            )
          }
        ) | from_entries) as $merged_hooks |

        # Final: project settings with merged hooks, without enabledPlugins
        $project | del(.enabledPlugins) | .hooks = $merged_hooks
      ' "$PROJECT_SETTINGS")

      echo "$MERGED" | jq '.' > "$PROJECT_SETTINGS.tmp"
      mv "$PROJECT_SETTINGS.tmp" "$PROJECT_SETTINGS"
      info "  Merged settings.json (legacy hooks removed, template hooks added)"
    else
      cp "$TEMPLATE_SETTINGS" "$PROJECT_SETTINGS"
      info "  Copied template settings.json"
    fi
  else
    warn "  jq not found — cannot merge settings.json. Copy template manually."
  fi

  # --- 4. Update .gitignore ---
  if ! grep -qF '.agents/' "$PROJECT_DIR/.gitignore" 2>/dev/null; then
    echo '.agents/' >> "$PROJECT_DIR/.gitignore"
    info "  Added .agents/ to .gitignore"
  fi
  if ! grep -qF 'claude.local.sh' "$PROJECT_DIR/.gitignore" 2>/dev/null; then
    echo 'claude.local.sh' >> "$PROJECT_DIR/.gitignore"
    info "  Added claude.local.sh to .gitignore"
  fi
  if ! grep -qF '.claude/.template-checksums' "$PROJECT_DIR/.gitignore" 2>/dev/null; then
    echo '.claude/.template-checksums' >> "$PROJECT_DIR/.gitignore"
    info "  Added .claude/.template-checksums to .gitignore"
  fi
  if ! grep -qF '.claude/.template-version' "$PROJECT_DIR/.gitignore" 2>/dev/null; then
    echo '.claude/.template-version' >> "$PROJECT_DIR/.gitignore"
    info "  Added .claude/.template-version to .gitignore"
  fi

  # --- 5. Save template checksums + version ---
  compute_checksums "$TEMPLATE_DIR" "$CHECKSUMS_FILE"
  info "  Saved template checksums"
  save_template_version "$TEMPLATE_DIR"

  # --- 6. Install skills ---
  info "Installing skills from AGENT_SETUP.md..."
  if [ -f "$PROJECT_DIR/AGENT_SETUP.md" ]; then
    CLAUDE_PROJECT_DIR="$PROJECT_DIR" "$PROJECT_DIR/.claude/hooks/agent-setup.sh" || true
  fi

  echo ""
  info "========================================"
  info "  Init complete!"
  info "========================================"
  info ""
  info "Next steps:"
  info "  1. Review changes: git diff"
  info "  2. Create claude.local.sh with your proxy/API settings"
  info "  3. Commit: git add -A && git commit -m 'feat: adopt agent-setup template'"
  info "  4. Start Claude: ./claude.sh"
}

# ============================================
# Update mode: pull latest template
# ============================================
do_update() {
  TEMPLATE_DIR=$(clone_template)
  trap "rm -rf '$TEMPLATE_DIR'" EXIT

  info "Updating from template..."
  UPDATED=0

  # Infrastructure files: always overwrite
  INFRA_FILES=(
    "claude.sh"
    "update-from-template.sh"
    ".claude/RTK.md"
  )
  for f in "${INFRA_FILES[@]}"; do
    if [ -f "$TEMPLATE_DIR/$f" ]; then
      copy_file "$TEMPLATE_DIR/$f" "$PROJECT_DIR/$f"
      [ -x "$TEMPLATE_DIR/$f" ] && chmod +x "$PROJECT_DIR/$f"
      info "  Updated: $f"
      UPDATED=$((UPDATED + 1))
    fi
  done

  # Hooks: always overwrite
  for f in "$TEMPLATE_DIR"/.claude/hooks/*.sh; do
    [ -f "$f" ] || continue
    fname=$(basename "$f")
    copy_file "$f" "$PROJECT_DIR/.claude/hooks/$fname"
    chmod +x "$PROJECT_DIR/.claude/hooks/$fname"
    info "  Updated hook: $fname"
    UPDATED=$((UPDATED + 1))
  done

  # mcp.json: only if not exists (users add their own MCP servers)
  if [ -f "$TEMPLATE_DIR/.claude/mcp.json" ] && [ ! -f "$PROJECT_DIR/.claude/mcp.json" ]; then
    copy_file "$TEMPLATE_DIR/.claude/mcp.json" "$PROJECT_DIR/.claude/mcp.json"
    info "  Created: .claude/mcp.json"
    UPDATED=$((UPDATED + 1))
  fi

  # .mcp.env.example: always overwrite (template may add new keys)
  if [ -f "$TEMPLATE_DIR/.mcp.env.example" ]; then
    copy_file "$TEMPLATE_DIR/.mcp.env.example" "$PROJECT_DIR/.mcp.env.example"
    info "  Updated: .mcp.env.example"
    UPDATED=$((UPDATED + 1))
  fi

  # Config files: only if user hasn't modified
  for f in "$TEMPLATE_DIR"/.claude/commands/*.md "$TEMPLATE_DIR"/.claude/agents/*.md; do
    [ -f "$f" ] || continue
    # Get relative path
    relpath="${f#$TEMPLATE_DIR/}"
    project_file="$PROJECT_DIR/$relpath"

    if [ ! -f "$project_file" ]; then
      # File doesn't exist in project — copy it
      copy_file "$f" "$project_file"
      info "  Created: $relpath"
      UPDATED=$((UPDATED + 1))
    else
      # Check if user has modified it
      stored_hash=$(get_stored_checksum "$relpath")
      if [ -n "$stored_hash" ]; then
        current_hash=$(shasum -a 256 "$project_file" | cut -d' ' -f1)
        if [ "$current_hash" = "$stored_hash" ]; then
          # User hasn't modified — safe to overwrite
          copy_file "$f" "$project_file"
          info "  Updated: $relpath"
          UPDATED=$((UPDATED + 1))
        else
          warn "  Skipped: $relpath (locally modified)"
        fi
      else
        warn "  Skipped: $relpath (no stored checksum, may be locally modified)"
      fi
    fi
  done

  # Bundled skills: copy template skill directories (skip symlinks from skills CLI)
  if [ -d "$TEMPLATE_DIR/.claude/skills" ]; then
    for skill_dir in "$TEMPLATE_DIR"/.claude/skills/*/; do
      [ -d "$skill_dir" ] || continue
      skill_name=$(basename "$skill_dir")
      project_skill="$PROJECT_DIR/.claude/skills/$skill_name"

      # Skip if project has a symlink (managed by skills CLI)
      if [ -L "$project_skill" ]; then
        continue
      fi

      if [ ! -d "$project_skill" ]; then
        # Skill doesn't exist — copy it
        mkdir -p "$project_skill"
        cp -r "$skill_dir"* "$project_skill/"
        info "  Created skill: $skill_name"
        UPDATED=$((UPDATED + 1))
      else
        # Check if user has modified it (compare SKILL.md checksum)
        relpath=".claude/skills/$skill_name/SKILL.md"
        stored_hash=$(get_stored_checksum "$relpath")
        if [ -n "$stored_hash" ]; then
          current_hash=$(shasum -a 256 "$project_skill/SKILL.md" | cut -d' ' -f1)
          if [ "$current_hash" = "$stored_hash" ]; then
            cp -r "$skill_dir"* "$project_skill/"
            info "  Updated skill: $skill_name"
            UPDATED=$((UPDATED + 1))
          else
            warn "  Skipped skill: $skill_name (locally modified)"
          fi
        else
          warn "  Skipped skill: $skill_name (no stored checksum)"
        fi
      fi
    done
  fi

  # Update checksums + version
  compute_checksums "$TEMPLATE_DIR" "$CHECKSUMS_FILE"
  save_template_version "$TEMPLATE_DIR"

  echo ""
  info "Update complete. $UPDATED file(s) updated."
}

# ============================================
# Main
# ============================================
case "${1:-}" in
  --init)
    do_init
    ;;
  --help|-h)
    echo "Usage: $0 [--init]"
    echo ""
    echo "  --init    Bootstrap project from agent-setup template (first-time setup)"
    echo "  (no args) Update infrastructure files from latest template"
    ;;
  "")
    do_update
    ;;
  *)
    error "Unknown option: $1"
    echo "Usage: $0 [--init]"
    exit 1
    ;;
esac
