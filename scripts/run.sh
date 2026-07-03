#!/usr/bin/env bash
# 使用项目虚拟环境运行命令；无参数时启动 Web 服务
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
PIP="$ROOT/.venv/bin/pip"

if [[ ! -x "$PYTHON" ]]; then
  echo "正在创建虚拟环境..."
  python3 -m venv "$ROOT/.venv"
  "$PIP" install -r "$ROOT/requirements.txt"
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export HF_HUB_DISABLE_SYMLINKS_WARNING="${HF_HUB_DISABLE_SYMLINKS_WARNING:-1}"
cd "$ROOT"

if [[ $# -eq 0 ]]; then
  exec "$PYTHON" scripts/run_server.py
else
  exec "$PYTHON" "$@"
fi
