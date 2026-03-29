#!/bin/bash
set -euo pipefail

echo "=== Claude Orchestration Framework Setup ==="
echo ""

# Color helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Helper: ask to install something
offer_install() {
  local name="$1"
  local install_cmd="$2"
  local description="${3:-}"
  echo ""
  if [ -n "$description" ]; then
    echo "  $description"
  fi
  printf "  Install %s now? [Y/n] " "$name"
  read -r REPLY
  REPLY="${REPLY:-Y}"
  if [[ "$REPLY" =~ ^[Yy]$ ]]; then
    echo "  Installing $name..."
    eval "$install_cmd"
    if [ $? -eq 0 ]; then
      printf "  ${GREEN}INSTALLED${NC}  %s\n" "$name"
      return 0
    else
      printf "  ${RED}FAILED${NC}  %s installation failed\n" "$name"
      return 1
    fi
  else
    printf "  ${YELLOW}SKIPPED${NC}  %s\n" "$name"
    return 1
  fi
}

# ============================================================
# Phase 0: Ensure common bin paths are on PATH
# ============================================================
# Claude CLI installs to ~/.claude/bin/ which may not be on PATH yet
for p in "$HOME/.claude/bin" "/opt/homebrew/bin" "$HOME/.local/bin"; do
  if [ -d "$p" ] && [[ ":$PATH:" != *":$p:"* ]]; then
    export PATH="$p:$PATH"
  fi
done

# ============================================================
# Phase 1: Foundation — Homebrew (needed for everything else)
# ============================================================
echo "--- Checking foundations ---"

if command -v brew &>/dev/null; then
  printf "  ${GREEN}OK${NC}  brew found: %s\n" "$(command -v brew)"
else
  printf "  ${RED}MISSING${NC}  Homebrew not found\n"
  offer_install "Homebrew" \
    '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"' \
    "Homebrew is needed to install tmux, python3, node, git, and ffmpeg." || {
    echo ""
    echo "  Homebrew is required to install dependencies. Install it manually:"
    echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
  }
  # Ensure brew is on PATH for this session (Apple Silicon path)
  if [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
fi

# ============================================================
# Phase 2: Core tools — git, python3, tmux, node/npm, claude
# ============================================================
echo ""
echo "--- Checking core tools ---"

# Git
if command -v git &>/dev/null; then
  printf "  ${GREEN}OK${NC}  git found: %s\n" "$(git --version)"
else
  printf "  ${RED}MISSING${NC}  git not found\n"
  offer_install "git" "brew install git" || {
    echo "  git is required. Install with: brew install git"
    exit 1
  }
fi

# Python 3
if command -v python3 &>/dev/null; then
  printf "  ${GREEN}OK${NC}  python3 found: %s\n" "$(python3 --version 2>&1)"
else
  printf "  ${RED}MISSING${NC}  python3 not found\n"
  offer_install "python3" "brew install python3" || {
    echo "  python3 is required. Install with: brew install python3"
    exit 1
  }
fi

# tmux
if command -v tmux &>/dev/null; then
  printf "  ${GREEN}OK${NC}  tmux found: %s\n" "$(tmux -V)"
else
  printf "  ${RED}MISSING${NC}  tmux not found\n"
  offer_install "tmux" "brew install tmux" || {
    echo "  tmux is required. Install with: brew install tmux"
    exit 1
  }
fi

# Claude Code (prefer brew install, fallback to npm)
if command -v claude &>/dev/null; then
  printf "  ${GREEN}OK${NC}  claude found: %s\n" "$(command -v claude)"
else
  printf "  ${RED}MISSING${NC}  Claude Code not found\n"
  offer_install "Claude Code" "brew install claude-code" \
    "Claude Code is the AI agent CLI that powers this framework." || {
    echo "  Claude Code is required. Install with: brew install claude-code"
    echo "  Then authenticate with: claude auth"
    exit 1
  }
  echo ""
  echo "  You may need to authenticate Claude Code before continuing:"
  echo "  Run: claude auth"
  printf "  Have you already authenticated? [Y/n] "
  read -r REPLY
  REPLY="${REPLY:-Y}"
  if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo "  Please run 'claude auth' in another terminal, then re-run this setup."
    exit 1
  fi
fi

# ============================================================
# Phase 3: Optional tools
# ============================================================
echo ""
echo "--- Checking optional tools ---"

# GitHub CLI
if command -v gh &>/dev/null; then
  printf "  ${GREEN}OK${NC}  gh (GitHub CLI) found: %s\n" "$(gh --version | head -1)"
  # Check auth status
  if gh auth status &>/dev/null; then
    printf "  ${GREEN}OK${NC}  gh authenticated\n"
  else
    printf "  ${YELLOW}NOTE${NC}  gh installed but not authenticated\n"
    echo "  Run 'gh auth login' to authenticate for repo creation and push."
  fi
else
  printf "  ${YELLOW}MISSING${NC}  gh (GitHub CLI) not found\n"
  offer_install "GitHub CLI" "brew install gh" \
    "GitHub CLI is used to create private repos and push during setup." || {
    printf "  ${YELLOW}SKIP${NC}  You can install later: brew install gh\n"
    printf "  ${YELLOW}SKIP${NC}  Without gh, you'll need to create the GitHub repo manually.\n"
  }
fi

if command -v ffmpeg &>/dev/null; then
  printf "  ${GREEN}OK${NC}  ffmpeg found (for voice notes)\n"
else
  printf "  ${YELLOW}MISSING${NC}  ffmpeg not found (needed for voice notes)\n"
  offer_install "ffmpeg" "brew install ffmpeg" \
    "ffmpeg enables voice message transcription and synthesis." || {
    printf "  ${YELLOW}SKIP${NC}  Voice notes won't work without ffmpeg. You can install later: brew install ffmpeg\n"
  }
fi

# ============================================================
# Phase 4: cc alias (claude --dangerously-skip-permissions)
# ============================================================
echo ""
echo "--- Checking agent alias ---"

# Detect shell config file (needed for alias check and potential addition)
SHELL_NAME="$(basename "$SHELL")"
if [ "$SHELL_NAME" = "zsh" ]; then
  SHELL_RC="$HOME/.zshrc"
elif [ "$SHELL_NAME" = "bash" ]; then
  SHELL_RC="$HOME/.bashrc"
else
  SHELL_RC="$HOME/.profile"
fi

# Check for cc alias in shell RC file (command -v fails in non-interactive tmux sessions)
if grep -q "alias cc=" "$SHELL_RC" 2>/dev/null; then
  printf "  ${GREEN}OK${NC}  cc alias found in %s\n" "$SHELL_RC"
else
  printf "  ${YELLOW}NOTE${NC}  The 'cc' alias is not configured.\n"
  echo "  The orchestration framework uses 'cc' to launch agent sessions without"
  echo "  permission dialogs (which stall automated agents)."
  echo ""
  echo "  cc='claude --dangerously-skip-permissions'"

  echo ""
  printf "  Add to %s? [Y/n] " "$SHELL_RC"
  read -r REPLY
  REPLY="${REPLY:-Y}"
  if [[ "$REPLY" =~ ^[Yy]$ ]]; then
    echo "" >> "$SHELL_RC"
    echo "# Claude Orchestration Framework — skip-permissions alias for agent sessions" >> "$SHELL_RC"
    echo "alias cc='claude --dangerously-skip-permissions'" >> "$SHELL_RC"
    printf "  ${GREEN}ADDED${NC}  alias written to %s\n" "$SHELL_RC"
    echo "  Run 'source $SHELL_RC' or open a new terminal for it to take effect."
    alias cc='claude --dangerously-skip-permissions' 2>/dev/null || true
  else
    printf "  ${YELLOW}SKIPPED${NC}  You can add it manually later: alias cc='claude --dangerously-skip-permissions'\n"
  fi
fi

# ============================================================
# Phase 4.5: Orchestration infrastructure
# ============================================================
echo ""
echo "--- Checking orchestration infrastructure ---"

if [ -d "$HOME/.config/orchestration/manifests" ]; then
  MANIFEST_COUNT=$(ls "$HOME/.config/orchestration/manifests/"*.json 2>/dev/null | wc -l | tr -d ' ')
  printf "  ${GREEN}OK${NC}  Orchestration home exists ($MANIFEST_COUNT project(s) registered)\n"
else
  printf "  ${YELLOW}NOTE${NC}  First project on this machine. Creating orchestration infrastructure...\n"
  mkdir -p "$HOME/.config/orchestration/manifests"
  printf "  ${GREEN}OK${NC}  Created ~/.config/orchestration/manifests/\n"
fi

# ============================================================
# Phase 5: Launch setup agent
# ============================================================
echo ""
echo "=== All prerequisites met ==="

# Check if a project brief input file exists for autonomous mode
if [ -f "project-brief-input.md" ]; then
  echo "Found project-brief-input.md — launching in autonomous mode."
  echo "The setup agent will read the brief and configure everything automatically."
  echo ""
  exec claude --dangerously-skip-permissions "You are the setup agent for a new project using the Claude Orchestration Framework. Read .orchestration/setup-brief.md for your complete instructions. A project brief input file exists at project-brief-input.md — read it and use it to skip interactive questions. Execute all steps including Step 7.5 (Launch Operational Stack). The end state must be a fully operational CPO with active cron loops, active subconscious, and live communications."
else
  echo "Launching Claude as the interactive setup agent..."
  echo "The setup agent will configure this project for your use case."
  echo ""
  exec claude --dangerously-skip-permissions "You are the setup agent for a new project using the Claude Orchestration Framework. Read .orchestration/setup-brief.md for your complete instructions. Begin the interactive setup now."
fi
