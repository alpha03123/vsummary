#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_NAME="vsummary"
CONDA_BIN="${CONDA_EXE:-}"

# Finder does not inherit the interactive shell's Homebrew PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  if [ -z "$CONDA_BIN" ] || [ ! -x "$CONDA_BIN" ]; then
    if command -v conda >/dev/null 2>&1; then
      CONDA_BIN="$(command -v conda)"
    else
      for candidate in "$HOME/miniconda3/bin/conda" "$HOME/anaconda3/bin/conda" "$HOME/mambaforge/bin/conda" "$HOME/miniforge3/bin/conda" "/opt/homebrew/Caskroom/miniforge/base/bin/conda"; do
        if [ -x "$candidate" ]; then
          CONDA_BIN="$candidate"
          break
        fi
      done
    fi
  fi

  if [ -z "$CONDA_BIN" ] || [ ! -x "$CONDA_BIN" ]; then
    echo "Conda was not found. Install it, then create the source environment with environment.cpu.yml."
    exit 1
  fi

  ENV_PATH="$("$CONDA_BIN" env list | awk -v name="$ENV_NAME" '$1 == name { print $NF; exit }')"
  PYTHON="$ENV_PATH/bin/python"
  if [ -z "$ENV_PATH" ] || [ ! -x "$PYTHON" ]; then
    echo "Conda environment '$ENV_NAME' was not found."
    echo "Run: conda env create -f environment.cpu.yml"
    exit 1
  fi
fi

MYSQL_HOME="${VSUMMARY_MYSQL_HOME:-}"
if [ -z "$MYSQL_HOME" ] && command -v brew >/dev/null 2>&1; then
  MYSQL_HOME="$(brew --prefix mysql@8.4 2>/dev/null || true)"
fi
if [ ! -x "$MYSQL_HOME/bin/mysqld" ]; then
  echo "MySQL 8.4 was not found. Run: brew install mysql@8.4"
  echo "Or set VSUMMARY_MYSQL_HOME to your MySQL installation."
  exit 1
fi
if [ ! -f "$ROOT/src/frontend/dist/index.html" ]; then
  echo "Build the frontend first: cd src/frontend && npm ci && npm run build"
  exit 1
fi

PORT="${VSUMMARY_PORT:-4173}"
if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Stop the running app or set VSUMMARY_PORT."
  exit 1
fi

export PYTHONPATH="$ROOT/src"
export HF_HOME="$ROOT/data/huggingface"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
ARGS=(--host 127.0.0.1 --port "$PORT" --managed-mysql-home "$MYSQL_HOME")
if [ -n "${VSUMMARY_DATA_ROOT:-}" ]; then
  ARGS+=(--managed-data-root "$VSUMMARY_DATA_ROOT")
fi

# Keep the server attached to this terminal; Ctrl+C also shuts down private MySQL.
"$PYTHON" -m backend.api.http.server "${ARGS[@]}" &
SERVER_PID=$!
cleanup() {
  kill -INT "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
for ((attempt=0; attempt<90; attempt++)); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    wait "$SERVER_PID"
    exit 1
  fi
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    echo "VSummary: http://127.0.0.1:$PORT — close this terminal or press Ctrl+C to stop."
    open "http://127.0.0.1:$PORT"
    wait "$SERVER_PID"
    exit $?
  fi
  sleep 1
done
echo "VSummary did not become ready; check the error above."
exit 1
