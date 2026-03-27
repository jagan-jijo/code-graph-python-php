#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

log() {
  printf '[code-graph] %s\n' "$*"
}

fail() {
  printf '[code-graph] ERROR: %s\n' "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

pick_python() {
  if command_exists python3; then
    echo "python3"
    return
  fi
  if command_exists python; then
    echo "python"
    return
  fi
  if command_exists py; then
    echo "py -3"
    return
  fi
  echo ""
}

PYTHON_CMD="$(pick_python)"
[ -n "$PYTHON_CMD" ] || fail "No Python interpreter found. Install Python 3.11+ and rerun start.sh."
command_exists npm || fail "npm is not installed or not on PATH. Install Node.js 18+ and rerun start.sh."

log "Project root: $ROOT_DIR"
log "Using Python command: $PYTHON_CMD"

if [ ! -d ".venv" ]; then
  log "Creating virtual environment in .venv"
  eval "$PYTHON_CMD -m venv .venv"
else
  log "Virtual environment already exists"
fi

if [ -x ".venv/Scripts/python.exe" ]; then
  VENV_PIP=".venv/Scripts/pip.exe"
elif [ -x ".venv/bin/python" ]; then
  VENV_PIP=".venv/bin/pip"
else
  fail "Virtual environment was created, but its Python executable was not found."
fi

log "Installing backend dependencies from requirements.txt"
"$VENV_PIP" install -r requirements.txt

if [ ! -d "node_modules" ]; then
  log "Installing root npm dependencies"
  npm install
else
  log "Root npm dependencies already installed"
fi

if [ -f "frontend/package.json" ]; then
  if [ ! -d "frontend/node_modules" ]; then
    log "Installing frontend npm dependencies"
    (
      cd frontend
      npm install
    )
  else
    log "Frontend npm dependencies already installed"
  fi
fi

missing_runtime_files=()
[ -f "backend/main.py" ] || missing_runtime_files+=("backend/main.py")
[ -f "frontend/package.json" ] || missing_runtime_files+=("frontend/package.json")

if [ ${#missing_runtime_files[@]} -gt 0 ]; then
  log "Project rebuild is incomplete. Missing runtime files:"
  for path in "${missing_runtime_files[@]}"; do
    log "  - $path"
  done
  fail "Restore those files, then rerun ./start.sh or npm start."
fi

open_browser() {
  sleep 4
  if command_exists powershell.exe; then
    log "Opening browser at http://127.0.0.1:3000"
    powershell.exe -NoProfile -Command "Start-Process 'http://127.0.0.1:3000'" >/dev/null 2>&1 || true
    return
  fi
  if command_exists cmd.exe; then
    log "Opening browser at http://127.0.0.1:3000"
    cmd.exe /c start "" "http://127.0.0.1:3000" >/dev/null 2>&1 || true
    return
  fi
  if command_exists xdg-open; then
    log "Opening browser at http://127.0.0.1:3000"
    xdg-open "http://127.0.0.1:3000" >/dev/null 2>&1 || true
  fi
}

log "Starting backend and frontend via npm start"
open_browser &
exec npm start
