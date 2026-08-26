# 排障指南（Troubleshooting）

本文档汇总 FileKG 本地部署与演示时的常见问题。启动后可在 Web UI **系统** 页查看自检，或访问 `GET /health/diagnostics`。

## 快速自检

```bash
curl -s http://localhost:8765/health/diagnostics | python -m json.tool
```

| 检查项 | 正常 | 异常时的含义 |
|--------|------|----------------|
| `embedding` | `sentence_transformers` / `fastembed` | `hash` 仅占位，语义检索几乎不可用 |
| `graph_index` | 有 `graph_store.json` | 尚未索引任何目录 |
| `chroma_index` | Chroma 目录非空 | 向量库未建立 |
| `deepseek_rag` | 可选 | 未配置 API Key 时 RAG 不可用 |

## 嵌入模型无法下载

**现象**：日志出现 `OSError` / `ConnectionError`，自检 `embedding` 为 `hash`。

**处理**：

1. 安装依赖：`pip install sentence-transformers` 或 `fastembed`
2. 运行：`python scripts/setup_models.py`
3. 国内网络可在 `.env` 设置镜像：
   ```bash
   HF_ENDPOINT=https://hf-mirror.com
   ```
4. 确认后重启服务，自检应显示非 `hash` 后端。

## 使用 hash 占位后端

**现象**：服务能启动，但检索结果随机或无关。

**原因**：`FILEKG_EMBEDDING_BACKEND=hash` 或模型加载失败时的降级。

**处理**：按上一节安装真实嵌入模型。Docker 演示镜像默认使用 hash 以便快速构建；本地开发请安装 `sentence-transformers`。

## 页面提示「未加载索引」

**现象**：旧版需手动点「确认加载全局索引」。

**当前默认**：`config.yaml` 中 `api.manual_load: false`，服务启动后会**后台自动加载**图与检索引擎。

若仍出现该提示：

1. 确认 `config.yaml` 中 `manual_load: false`
2. 轮询 `/health`，等待 `search_ready: true`
3. 若需恢复手动模式，设 `manual_load: true` 并在 UI 确认加载

## 尚未建立索引

**现象**：自检 `graph_index` / `chroma_index` 警告，检索无结果。

**处理**：

```bash
python scripts/generate_dataset.py          # 可选：示例数据
python scripts/index_directory.py data/dataset --clear
python scripts/run_server.py
```

## Chroma 锁或损坏

**现象**：`sqlite3.OperationalError: database is locked` 或索引后检索异常。

**处理**：

1. 停止所有 FileKG 进程（含多个 uvicorn 实例）
2. 删除 `data/chroma` 后重新索引：
   ```bash
   rm -rf data/chroma
   python scripts/index_directory.py /path/to/dir --clear
   ```

## Neo4j 连接失败

**现象**：日志 `Neo4j 不可用，回退到本地 JSON 图存储`。

**说明**：无 Neo4j 时系统自动使用 `data/graph_store.json`，功能子集可用。

**可选启用 Neo4j**：

```bash
docker compose --profile neo4j up -d neo4j
# config.yaml 中 neo4j.uri 默认 bolt://localhost:7687
```

## 大目录索引很慢

**建议**：

- 批量索引进程设置 `FILEKG_INDEX_FAST=1`（跳过 LLM 摘要，边扫边写）
- 首次检索前不构建全量 BM25 语料（默认 `build_corpus: false`）
- 限制文件数：`python scripts/index_directory.py ~/Docs --max-files 5000`

## DeepSeek RAG 不可用

1. 在 `.env` 设置 `DEEPSEEK_API_KEY`
2. `config.yaml` 中 `deepseek.enabled: true`
3. 运行 `python scripts/setup_rag.py` 并按提示索引

## Docker 演示

```bash
chmod +x scripts/docker-demo.sh
./scripts/docker-demo.sh
```

容器内预置示例数据与 hash 嵌入。要获得更好检索效果，请在宿主机按 Quick Demo 安装真实模型。

## 仍无法解决？

1. 查看服务日志（uvicorn 输出）
2. 导出自检 JSON 并附带 `config.yaml`（勿含 API Key）
3. 在 [Issues](https://github.com/S1M0nLEE/File-Describer/issues) 反馈
