# FileKG

基于文件描述符（FileDescriptor）的知识图谱检索系统：离线索引（Neo4j + Chroma）+ 图关系扩展 + 多因子排序。

## 环境要求

- Python 3.11+
- **图数据库（二选一）**
  - **Neo4j 模式（推荐）**：ZIP 安装，无需 Docker（见下方）
  - **本地模式**：图数据存于 `data/local_graph.json`（`.env` 设 `FILEKG_GRAPH_BACKEND=local`）
- 可选：Ollama（LLM 摘要 / 查询解析）

## 一键配置（Windows）

```powershell
cd filekg
.\scripts\setup.ps1
```

将自动：创建 venv、安装依赖、加载 `.env`、下载 BGE 模型、索引 `code_dependency`、运行评估。

检查环境：`.\scripts\check_env.ps1`  
启动 API：`.\scripts\start_api.ps1`

## 快速开始（手动）

```powershell
cd filekg
.\scripts\load_env.ps1          # 加载 .env（FILEKG_GRAPH_BACKEND=local）
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python scripts/create_datasets.py --dataset all
python scripts/run_indexing.py data/datasets/code_dependency
pytest tests/ -q
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

### 安装 Neo4j（无 Docker，Windows）

```powershell
.\scripts\install_neo4j.ps1
.\scripts\start_neo4j.ps1
.\.venv\Scripts\python.exe scripts\set_neo4j_password.py
.\scripts\load_env.ps1
python scripts\run_indexing.py data\datasets\code_dependency
```

浏览器 http://localhost:7474（`neo4j` / `filekg123`）。停止：`.\scripts\stop_neo4j.ps1`

### 搜索示例

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"预算 Q1\", \"top_k\": 10}"
```

## 配置

所有参数集中在 `src/config.py`，复制 `.env.example` 为 `.env` 即可。主要变量：

| 变量 | 说明 | 默认 |
|------|------|------|
| `FILEKG_GRAPH_BACKEND` | `local` / `neo4j` / `auto` | `local` |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j 连接 | 见 `.env` |
| `FILEKG_SKIP_VISUAL` | 索引时跳过 CLIP（`0` 启用） | `1` |

## 项目结构

```
filekg/
├── data/datasets/          # 合成数据集
├── data/evaluation/        # 实验结果
├── src/
│   ├── config.py
│   ├── models/             # FileDescriptor, Folder, Project, Tag
│   ├── pipeline/           # 扫描、提取、摘要、向量、建图
│   ├── relations/          # 12 种关系解析器
│   ├── retrieval/          # 查询解析、向量检索、图扩展、排序
│   └── api/                # FastAPI /search
├── scripts/
│   ├── create_datasets.py
│   ├── run_indexing.py
│   ├── run_evaluation.py
│   └── download_hippocamp.py
└── tests/
```

## 关系类型

| 关系 | 说明 |
|------|------|
| IN_FOLDER | 文件 → 文件夹 |
| SAME_TYPE | 相同扩展名 |
| NEAR_IN_TIME | 修改时间邻近 |
| HAS_VERSION | 版本文件名 + 内容重叠 |
| DEPENDS_ON | import/require |
| REFERENCES | 文本中的路径引用 |
| CONTAINS | zip/json 成员 |
| SIMILAR_TO | FAISS 向量相似 |
| WORKFLOW_WITH | 访问序列 / 时间代理 |
| VISUALLY_SIMILAR_TO | CLIP 图像相似 |
| BELONGS_TO_PROJECT | 项目根标记 |
| TAGGED_WITH | 文件名 #tag / sidecar |

## 公开数据集拼装基准（filekg_main_public）

```powershell
.\scripts\load_env.ps1
python scripts/build_filekg_main.py --quick          # 或去掉 --quick 做更大规模
python scripts/run_public_benchmark.py --skip-build  # 构建+索引+评估+论文报告
```

输出：
- 数据集：`data/datasets/filekg_main_public/`
- 实验结果：`data/evaluation/experiment_data_public.json`
- 论文报告：`data/evaluation/paper_report.md`

## 评估

**四维实验矩阵（推荐，一键跑完全部数据集/基线/消融/鲁棒性）：**

```powershell
.\scripts\load_env.ps1
python scripts/run_experiment_matrix.py
python scripts/run_experiment_matrix.py --quick          # 仅 filekg_main + code_dependency
python scripts/run_experiment_matrix.py --datasets filekg_main_public --skip-create
```

输出：`data/evaluation/experiment_matrix_results.json`、`experiment_matrix_report.md`

单数据集：

```powershell
$env:PYTHONPATH = "."
python scripts/run_evaluation.py data/datasets/filekg_main
python scripts/run_evaluation.py data/datasets/code_dependency --ablation --robustness-retrieval
```

基线：BM25、VectorOnly、Vector+Metadata、Vector+SIMILAR_TO、FileKG-Full。

指标：MAP@20、NDCG@20、Recall@20、R_indirect@20、GraphDiscovery@20、ExplainCoverage@20。

**检索策略（真实场景）**：`Ranker` 以向量相似度为主（`alpha=1.0`），图/BM25/元数据仅作有界加分（`max_aux_boost`），避免 BM25 种子压过语义相关文件；图扩展邻居须满足 `min_graph_expand_vector` 才进入候选池。配置见 `src/config.py`（`metadata_filter_hard=False` 时扩展名等元数据不硬过滤 Chroma）。

语义 qrels 重建（索引后必跑）：

```powershell
python scripts/rebuild_qrels.py data/datasets/filekg_main_public
```

结果输出至 `data/evaluation/experiment_data.json` 与 `report.md`。

## HippoCamp 数据集

```powershell
pip install huggingface_hub
python scripts/download_hippocamp.py --use-hf
```

## 消融实验

`run_evaluation.py --ablation` 会依次禁用 SIMILAR_TO、DEPENDS_ON 等关系并对比 FileKG-Full 指标。

## 许可证

研究/原型用途，按需调整依赖与模型授权。
