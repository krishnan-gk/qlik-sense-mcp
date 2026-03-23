#!/usr/bin/env bash
# =============================================================================
# Qlik Sense MCP + Gemini — New User Setup
# =============================================================================
# Run this once to set up your local environment:
#
#   bash setup/user_setup.sh
#
# Requirements: Python 3.12+, pip, internet access

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
fail() { echo -e "  ${RED}✗${NC}  $*"; }
step() { echo -e "\n${BOLD}$*${NC}\n$(printf '─%.0s' {1..50})"; }

echo -e "\n${BOLD}Qlik Sense MCP + Gemini — Setup${NC}"
echo "$(printf '=%.0s' {1..50})"

# ── 1. Python version check ───────────────────────────────────────────────────
step "1. Checking Python version"

PYTHON_CMD=""
for cmd in python3.12 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | awk '{print $2}')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 12 ]]; then
            PYTHON_CMD="$cmd"
            ok "Found $cmd ($version)"
            break
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    fail "Python 3.12+ required but not found"
    echo "  Install from https://python.org or via: brew install python@3.12"
    exit 1
fi

# ── 2. Install package with gemini extras ─────────────────────────────────────
step "2. Installing qlik-sense-mcp-server[gemini]"

if [[ -d ".venv" ]]; then
    ok "Virtual environment already exists (.venv)"
    PIP=".venv/bin/pip"
else
    echo "  Creating virtual environment..."
    "$PYTHON_CMD" -m venv .venv
    ok "Virtual environment created (.venv)"
    PIP=".venv/bin/pip"
fi

"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -e ".[gemini]"
ok "Packages installed"

# ── 3. Create .env from example ───────────────────────────────────────────────
step "3. Setting up .env file"

if [[ -f ".env" ]]; then
    ok ".env already exists — skipping (not overwriting)"
else
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
        ok ".env created from .env.example"
        warn "Edit .env with your credentials before continuing!"
    else
        fail ".env.example not found — please create .env manually"
        exit 1
    fi
fi

# ── 4. Reminder: fill in credentials ──────────────────────────────────────────
step "4. Required credentials"

echo "  Edit .env and set these variables:"
echo ""
echo "    QLIK_SERVER_URL       https://qlik-dev.ispot.tv"
echo "    QLIK_USER_DIRECTORY   ANALYTICSUSERS"
echo "    QLIK_USER_ID          firstname.lastname@ispot.tv"
echo "    QLIK_CLIENT_CERT_PATH /absolute/path/to/client.pem"
echo "    QLIK_CLIENT_KEY_PATH  /absolute/path/to/client_key.pem"
echo "    GEMINI_API_KEY        AIzaSy..."
echo ""
echo "  Get cert files from your Qlik admin (export from QMC)."
echo "  Get your Gemini API key at: https://aistudio.google.com/apikey"

# ── 5. Final instructions ─────────────────────────────────────────────────────
step "5. Next steps"

echo "  1. Fill in your .env file (see above)"
echo "  2. Validate setup:  .venv/bin/python setup/new_user.py"
echo "  3. Start chatting:  .venv/bin/qlik-gemini"
echo ""
echo -e "${GREEN}${BOLD}Setup complete!${NC} Fill in .env and run: .venv/bin/python setup/new_user.py"
echo ""
