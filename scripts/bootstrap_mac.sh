#!/usr/bin/env bash
# macOS 一键初始化：依赖 → 模型 → 示例数据 → 索引
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

chmod +x scripts/run.sh

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

set -a
# shellcheck disable=SC1091
[[ -f .env ]] && source .env
set +a
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HUB_DISABLE_SYMLINKS_WARNING=1

.venv/bin/pip install -r requirements.txt

.venv/bin/python scripts/setup_models.py

if [[ ! -d data/dataset ]] || [[ -z "$(ls -A data/dataset 2>/dev/null)" ]]; then
  .venv/bin/python scripts/generate_dataset.py
fi

.venv/bin/python scripts/index_directory.py data/dataset --clear

echo ""
echo "初始化完成。启动服务："
echo "  ./scripts/run.sh"
echo "  浏览器打开 http://localhost:8765"
