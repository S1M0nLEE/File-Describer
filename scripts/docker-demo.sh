#!/usr/bin/env bash
# 一键启动 Docker 演示栈（含示例数据集与索引）
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> 构建并启动 FileKG（http://localhost:8765）"
docker compose up --build -d filekg

echo "==> 等待健康检查…"
for i in $(seq 1 30); do
  if curl -sf http://localhost:8765/health >/dev/null 2>&1; then
    echo "服务已就绪。"
    echo "打开浏览器: http://localhost:8765"
    echo "自检 API:   http://localhost:8765/health/diagnostics"
    exit 0
  fi
  sleep 2
done

echo "服务启动超时，请查看日志: docker compose logs filekg"
exit 1
