#!/usr/bin/env bash
# 从 Git 全历史中永久移除敏感/ bulky 路径（重写历史，不可逆）。
#
# 用法:
#   ./scripts/purge_git_history.sh          # dry-run（仅打印将执行的命令）
#   ./scripts/purge_git_history.sh --apply  # 实际重写本地历史
#
# 前置: brew install git-filter-repo
# 完成后需 force push（脚本会提示）:
#   git push --force origin main

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APPLY=false
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=true
fi

# --invert-paths：从全部历史中删除这些路径（勿漏此参数）
PATHS=(
  "说明文档.md"
  "data/dataset"
  "data/datasets"
  "data/evaluation"
  "data/robustness_workspace"
  "data/workflow_log.jsonl"
)

echo "=== File-Describer 历史清理 ==="
echo "仓库: $ROOT"
echo "将从全部历史中删除以下路径:"
printf '  - %s\n' "${PATHS[@]}"
echo

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "未找到 git-filter-repo。请先安装:"
  echo "  brew install git-filter-repo"
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "工作区有未提交改动，请先 commit 或 stash 后再运行 --apply。"
  exit 1
fi

ARGS=(--invert-paths)
for p in "${PATHS[@]}"; do
  ARGS+=(--path "$p")
done

CMD=(git filter-repo --force "${ARGS[@]}")

if [[ "$APPLY" == false ]]; then
  echo "[dry-run] 将执行:"
  printf '  %q ' "${CMD[@]}"
  echo
  echo
  echo "确认后运行: $0 --apply"
  echo "然后: git remote add origin <url>   # filter-repo 会移除 remote"
  echo "      git push --force origin main"
  exit 0
fi

echo "开始重写历史（可能需要数分钟）..."
"${CMD[@]}"

echo
echo "完成。请重新添加 remote 并 force push:"
echo "  git remote add origin https://github.com/S1M0nLEE/File-Describer.git"
echo "  git push --force origin main"
