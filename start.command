#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_NAME="vsummary"
CONDA_BIN="${CONDA_EXE:-}"

cd "$ROOT"

if [ -z "$CONDA_BIN" ] || [ ! -x "$CONDA_BIN" ]; then
  if command -v conda >/dev/null 2>&1; then
    CONDA_BIN="$(command -v conda)"
  else
    for candidate in "$HOME/miniconda3/bin/conda" "$HOME/anaconda3/bin/conda" "$HOME/mambaforge/bin/conda"; do
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

ENV_PATH="$($CONDA_BIN env list | awk -v name="$ENV_NAME" '$1 == name { print $NF; exit }')"
PYTHON="$ENV_PATH/bin/python"
if [ -z "$ENV_PATH" ] || [ ! -x "$PYTHON" ]; then
  echo "Conda environment '$ENV_NAME' was not found."
  echo "Run: conda env create -f environment.cpu.yml"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm was not found. Install Node.js 18 or newer."
  exit 1
fi

mkdir -p "$ROOT/data/logs"
if ! lsof -iTCP:8001 -sTCP:LISTEN >/dev/null 2>&1; then
  nohup "$PYTHON" -m backend.api.http.server --host 127.0.0.1 --port 8001 \
    >"$ROOT/data/logs/backend.log" 2>&1 &
fi
if ! lsof -iTCP:4173 -sTCP:LISTEN >/dev/null 2>&1; then
  (
    cd "$ROOT/src/frontend"
    nohup npm run dev >"$ROOT/data/logs/frontend.log" 2>&1 &
  )
fi

sleep 1
open "http://127.0.0.1:4173"
