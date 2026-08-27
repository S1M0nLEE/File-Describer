# 简历表述参考（真实口径）

> 以下内容均可在本仓库**代码、测试或 evaluation_snapshot.json** 中找到依据。面试时请区分「合成基准离线评测」与「生产环境表现」。

## 推荐写法（中文）

**FileKG — 个人文件知识图谱** | Python / FastAPI / Chroma / 图检索  
- 设计 VFE（volume 级 `file_id`）与插件化关系 Pipeline，实现 12+ 种文件关系自动发现  
- 实现可解释混合检索：向量种子 → 图扩展 → 多因子排序，Web UI 展示关系路径  
- 合成基准（`config_tois_eval`）：FileKG-Full MAP@20 **0.691**（238 文件 / 40 查询）；代码依赖 Serendipity@20 **0.522**
- 真实 benchmark（HippoCamp adam）：MAP@20 **0.618**（328 真实个人文件 / 123 查询，GraphDiscovery@20 **0.742**）
- 文件移动鲁棒性：volume `file_id` 关系保持率 **97.85%**（合成 benchmark，8 文件移动）
- 工程化：57 项自动化测试（含 HippoCamp fixture）、Ruff CI、Docker + 真实 benchmark CI job

## 推荐写法（English one-liner）

Built an explainable personal file knowledge graph (FastAPI + Chroma + graph expansion retrieval) with reproducible synthetic benchmarks (MAP@20 0.691; Serendipity@20 0.522 on code-dependency queries; 97.85% relation retention after file moves).

## 避免夸大

| 不建议写 | 建议改为 |
|----------|----------|
| 「生产级 97.9% 准确率」 | 「合成基准上 volume file_id 关系保持率 97.85%」 |
| 「全面优于所有向量检索」 | 「MAP 与 Vector+SIMILAR_TO 接近；Serendipity/GraphDiscovery 更优」 |
| 「SDR 行业领先」 | 「Serendipity@20（核心关系意外发现率）0.522，见 EVALUATION.md」 |
| 「BGE 中文 SOTA」 | 「默认 sentence-transformers/all-MiniLM-L6-v2，可换 BGE」 |

## 可现场演示

1. Quick Demo（5 分钟）：`README.md` → 检索「实验数据」「处理实验数据的 python 代码」  
2. 架构：`docs/ARCHITECTURE.md` 分层图  
3. 指标溯源：打开 `docs/evaluation_snapshot.json` + `docs/EVALUATION.md` 复现命令  

## 数字来源速查

见 [`evaluation_snapshot.json`](evaluation_snapshot.json)，由 `python scripts/export_public_metrics.py` 生成。
