# FileKG Architecture

> 一页读懂代码结构与数据流。仓库代号 **FileKG**，GitHub 名 **File-Describer**。

## 目标

为本地文件建立**虚拟文件实体（VFE）**，自动发现文件间关系，并支持**可解释的混合检索**（向量种子 + 图扩展 + 多因子排序）。

## 分层架构

```
┌─────────────────────────────────────────────────────────┐
│  Web UI + FastAPI (src/api/)                            │
│  检索 / 索引 / RAG / 图可视化 / 增量监控                  │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  Search (src/search/)                                   │
│  IntentParser → Chroma 种子 → GraphExpander → Ranker    │
└───────────────┬─────────────────────┬───────────────────┘
                │                     │
┌───────────────▼──────────┐  ┌───────▼──────────────────┐
│  Indexing (src/indexing/)│  │  Relations (src/relations/)│
│  扫描 / 提取 / 嵌入 / VFE │  │  插件化关系发现 Pipeline   │
└───────────────┬──────────┘  └───────┬──────────────────┘
                │                     │
┌───────────────▼─────────────────────▼──────────────────┐
│  Storage                                               │
│  Chroma (向量) + Neo4j 或 MemoryGraphStore (本地 JSON)   │
└────────────────────────────────────────────────────────┘
```

## 核心模块

| 目录 | 职责 |
|------|------|
| `src/indexing/` | `scan_directory`、`build_descriptor`、`get_file_id`、文本/多模态提取、BGE 嵌入 |
| `src/relations/` | `RelationDiscoveryPipeline`：元数据 / 内容 / 版本 / 语义 / 工作流 / 视觉关系 |
| `src/search/` | `IntentParser`、`GraphExpander`、`MultiFactorRanker`、`SearchEngine` |
| `src/storage/` | `ChromaStore`、`MemoryGraphStore`、`Neo4jStore` 工厂 |
| `src/api/` | FastAPI 路由、静态前端、后台加载与 heartbeat |
| `src/rag/` | 本地文件 RAG（DeepSeek + 检索上下文） |
| `scripts/` | 数据集生成、索引、评测、服务启动 |

## 唯一入口（Canonical Path）

| 用途 | 命令 / 模块 |
|------|-------------|
| 启动 API | `python scripts/run_server.py` → `src.api.app:app` |
| 索引目录 | `python scripts/index_directory.py` → `IndexBuilder` |
| 检索实现 | `src.search.engine.SearchEngine` |
| 图存储 | `src.storage.factory.create_graph_store` |

**已废弃**（见 [`legacy/README.md`](../legacy/README.md)）：`src/pipeline/`、`src/retrieval/`、`src/api/main.py`、`scripts/run_indexing.py`（现转发到 IndexBuilder）。

研究脚本在 [`research/scripts/`](../research/scripts/)。

## 安全

本地默认 `127.0.0.1`；可选 Bearer Token 与索引路径 allowlist。详见 [SECURITY.md](SECURITY.md)。

## 索引流程

1. **扫描**：`scan_directory(root)` 遍历目录，跳过 `node_modules`、`.git` 等。
2. **描述符**：每个文件生成 `FileDescriptor`（路径、扩展名、摘要、嵌入向量、`file_id`）。
3. **存储**：节点与边写入图存储；向量写入 Chroma。
4. **关系**：`RelationDiscoveryPipeline.run()` 依次执行各 `RelationParser`，写入边表。

`file_id` 默认 **volume 模式**（inode / Windows File ID）：文件移动或重命名后身份不变，关系可保持。

## 检索流程

1. **意图解析**：从自然语言提取扩展名、时间范围、关键词（`IntentParser`）。
2. **向量种子**：Chroma ANN 召回 Top-N 相似文件。
3. **图扩展**：从种子出发 1-hop（可配置）沿关系边扩展，带关系类型与路径。
4. **排序**：加权融合语义 / 图 / 时间 / 规则 / 个性化因子（`MultiFactorRanker`）。
5. **解释**：返回排序因子与关系路径，供 UI 展示。

## 配置

| 文件 | 用途 |
|------|------|
| `config.yaml` | 日常运行默认配置 |
| `config_tois_eval.yaml` | 公开评测口径（无查询级 rescoring） |
| `.env` | `DEEPSEEK_API_KEY`、`HF_ENDPOINT` 等密钥 |

环境变量前缀：`FILEKG_`（见 `src/config.py` 的 `Settings`）。

## 依赖可选集

| 安装 | 能力 |
|------|------|
| `requirements.txt` | 核心索引、检索、API |
| `requirements-visual.txt` | CLIP 视觉相似、OpenCV、Whisper 等多模态 |

## 评测复现

```bash
python scripts/generate_evaluation_benchmark.py
export FILEKG_CONFIG=config_tois_eval.yaml
python scripts/run_evaluation.py --dataset code_dependency
python scripts/run_robustness.py
```

结果写入本地 `data/evaluation/`（已在 `.gitignore` 排除）。

公开摘要：[`docs/evaluation_snapshot.json`](../docs/evaluation_snapshot.json) · 说明：[`docs/EVALUATION.md`](../docs/EVALUATION.md)

## 测试

```bash
pytest tests/ -q
```

覆盖关系发现、意图解析、VFE/解释模块、API health smoke 等。
