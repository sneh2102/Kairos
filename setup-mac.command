#!/usr/bin/env bash
# Kairos one-shot macOS setup + launcher. Double-click it, or run: bash setup-mac.command
# Installs (if missing): Xcode CLT, Homebrew, git, python 3.12, node, tectonic,
# then creates the venv, installs deps, writes .env, and starts the app.
# Safe to re-run: every step is skipped when already done.
set -euo pipefail

REPO_URL="https://github.com/sneh2102/Kairos.git"
say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# --- Where to put the code ---------------------------------------------------
# If this file sits inside a checkout, use it; otherwise clone to ~/Kairos.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$HERE/server.py" ] && [ -d "$HERE/desktop" ]; then
  ROOT="$HERE"
else
  ROOT="$HOME/Kairos"
fi

# --- Xcode command line tools (provides git) ---------------------------------
if ! xcode-select -p >/dev/null 2>&1; then
  say "Installing Xcode Command Line Tools (a dialog will pop up - click Install)"
  xcode-select --install || true
  until xcode-select -p >/dev/null 2>&1; do sleep 5; done
fi

# --- Homebrew ----------------------------------------------------------------
if ! command -v brew >/dev/null 2>&1; then
  say "Installing Homebrew"
  echo "Homebrew needs your Mac password (the account must be an Administrator)."
  sudo -v  # cache sudo so the non-interactive installer doesn't abort
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
# brew isn't on PATH until shellenv is evaluated (Apple Silicon vs Intel paths)
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if [ -x "$b" ]; then eval "$("$b" shellenv)"; break; fi
done
command -v brew >/dev/null || { echo "Homebrew install failed - see errors above."; exit 1; }

say "Installing git, python 3.12, node, tectonic"
brew install git python@3.12 node tectonic
PY="$(brew --prefix python@3.12)/bin/python3.12"

# --- Code --------------------------------------------------------------------
if [ ! -f "$ROOT/server.py" ]; then
  say "Cloning Kairos into $ROOT"
  git clone "$REPO_URL" "$ROOT"
fi
cd "$ROOT"

# --- Python env --------------------------------------------------------------
say "Setting up Python environment"
# Rebuild a venv that's missing or built on an old Python (macOS system python is 3.9)
if [ ! -x venv/bin/python ] || ! venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  rm -rf venv
  "$PY" -m venv venv
fi
venv/bin/python -m pip install --upgrade pip
venv/bin/pip install -r requirements.txt
venv/bin/playwright install chromium

# --- .env --------------------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  say "Ollama Cloud API key (ollama.com -> Settings -> API keys). Press Enter to skip and add it in the app's Settings page."
  read -r -p "Paste key: " KEY || KEY=""
  if [ -n "$KEY" ]; then
    sed -i '' "s|^OLLAMA_API_KEY_1=.*|OLLAMA_API_KEY_1=$KEY|" .env
  fi
fi

# --- Desktop app -------------------------------------------------------------
say "Installing desktop app dependencies"
(cd desktop && npm install && node node_modules/electron/install.js)  # newer npm skips install scripts, so fetch the Electron binary explicitly

say "Done. Starting Kairos (re-run this file any time to launch it again)"
cd desktop && npm start
